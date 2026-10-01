#!/usr/bin/env python3
"""Connect two container interfaces with a dedicated veth pair, without OVS/IP."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

from frr_topology import TopologyError, run, run_json

LABEL = "io.route-ovs.vpcs"


def validate_name(value, interface=False):
    pattern = r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,14}" if interface else r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}"
    if not re.fullmatch(pattern, value) or (interface and value == "lo"):
        raise TopologyError("无效的{}: {!r}".format("接口名" if interface else "容器名", value))


class Manager:
    def __init__(self, path, image):
        self.path = path.absolute()
        self.image = image
        self.state = {"version": 2, "pcs": {}}
        if self.path.exists():
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if saved.get("version") == 1 and not saved.get("pcs"):
                pass
            elif saved.get("version") == 2 and isinstance(saved.get("pcs"), dict):
                self.state = saved
            else:
                raise TopologyError("发现旧版 OVS VPCS 或无效记录，请先用旧版工具清理；不会自动改接旧连接")
        self.prefix = [] if os.geteuid() == 0 else ["sudo", "-n"]

    def save(self):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".vpcs-",
                                             dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(self.state, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(temporary), str(self.path))
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def authorize(self):
        for tool in ("docker", "ip", "nsenter"):
            if not shutil.which(tool):
                raise TopologyError("宿主机缺少命令: " + tool)
        if self.prefix:
            if not shutil.which("sudo"):
                raise TopologyError("创建 veth 需要 sudo 或 root")
            try:
                run(["sudo", "-n", "true"])
            except TopologyError:
                if not sys.stdin.isatty():
                    raise TopologyError("创建 veth 需要 sudo 权限，请在宿主机终端执行并完成验证；未创建容器或接口")
                if subprocess.run(["sudo", "-v"]).returncode:
                    raise TopologyError("sudo 验证失败；未创建容器或接口")

    def root(self, *args):
        return run(self.prefix + list(args))

    def inventory(self):
        return {line.split(" ", 1)[1]: line.split(" ", 1)[0] for line in
                run(["docker", "ps", "-a", "--no-trunc", "--format", "{{.ID}} {{.Names}}"] ).splitlines() if line}

    def inspect(self, name):
        return run_json(["docker", "inspect", "--type", "container", name])[0]

    def live(self, name):
        container = self.inspect(name)
        state = container["State"]
        if not state.get("Running") or state.get("Paused") or state.get("Restarting") or state.get("Pid", 0) <= 0:
            raise TopologyError("容器未正常运行: " + name)
        if container.get("HostConfig", {}).get("NetworkMode") == "host":
            raise TopologyError("不允许向 host 网络容器添加接口: " + name)
        return container

    def links(self, container):
        return run_json(["docker", "exec", container["Id"], "ip", "-j", "-d", "link", "show"])

    def namespace(self, container):
        return run(["docker", "exec", container["Id"], "readlink", "/proc/self/ns/net"]).strip()

    def require_free(self, container, interface):
        if any(link["ifname"] == interface for link in self.links(container)):
            raise TopologyError("接口已存在，拒绝接入: {}.{}".format(container["Name"].lstrip("/"), interface))

    def require_same_process(self, container):
        current = self.live(container["Id"])
        if current["State"]["Pid"] != container["State"]["Pid"]:
            raise TopologyError("操作期间容器重启，请重试")

    def create_pair(self, connection, target, pc):
        token = connection["token"]
        endpoints = connection["endpoints"]
        self.root("ip", "link", "add", "name", endpoints[0]["temporary"],
                  "type", "veth", "peer", "name", endpoints[1]["temporary"])
        hosts = run_json(["ip", "-j", "-d", "link", "show"])
        for end in endpoints:
            created = next(link for link in hosts if link["ifname"] == end["temporary"])
            end.update(ifindex=created["ifindex"], mac=created["address"])
        self.save()
        # veth does not preserve an alias supplied to 'ip link add' on this host.
        for index, end in enumerate(endpoints):
            self.root("ip", "link", "set", "dev", end["temporary"], "alias", "route-ovs:" + token + ":" + str(index))
        for container, end in zip((target, pc), endpoints):
            self.require_same_process(container)
            self.require_free(container, end["interface"])
            pid = str(container["State"]["Pid"])
            self.root("ip", "link", "set", "dev", end["temporary"], "netns", pid)
            self.root("nsenter", "-t", pid, "-n", "ip", "link", "set", "dev", end["temporary"], "name", end["interface"])
            self.root("nsenter", "-t", pid, "-n", "ip", "link", "set", "dev", end["interface"], "up")
        actual = []
        for index, (container, end) in enumerate(zip((target, pc), endpoints)):
            self.require_same_process(container)
            link = next((link for link in self.links(container) if link["ifname"] == end["interface"]), None)
            if not link or link.get("ifalias") != "route-ovs:" + token + ":" + str(index):
                raise TopologyError("新建接口的归属校验失败")
            end.update(ifindex=link["ifindex"], mac=link["address"])
            actual.append(link)
        if actual[0].get("link_index") != actual[1]["ifindex"] or actual[1].get("link_index") != actual[0]["ifindex"]:
            raise TopologyError("新建接口并非彼此的 veth 对端")

    def add(self, target_name, target_interface, pc_name, pc_interface):
        for value in (target_name, pc_name):
            validate_name(value)
        for value in (target_interface, pc_interface):
            validate_name(value, interface=True)
        target = self.live(target_name)
        self.require_free(target, target_interface)
        inventory = self.inventory()
        existing = pc_name in inventory
        pc = self.live(pc_name) if existing else None
        if pc:
            self.require_free(pc, pc_interface)
            if pc["Id"] == target["Id"] or self.namespace(pc) == self.namespace(target):
                raise TopologyError("两端必须属于不同的网络命名空间")
        else:
            run_json(["docker", "image", "inspect", self.image])
        entry = self.state["pcs"].get(pc_name)
        if entry:
            if not pc or entry["container_id"] != pc["Id"]:
                raise TopologyError("PC 容器已被删除或替换，请先清理旧记录: " + pc_name)
            if any(c["phase"] != "ready" for c in entry["connections"]):
                raise TopologyError("PC 有未完成的操作，请先清理: " + pc_name)
        self.authorize()
        new_entry = entry is None
        if new_entry:
            entry = {"name": pc_name, "container_id": pc["Id"] if pc else None,
                     "owned": not existing, "creator": uuid.uuid4().hex if not existing else None,
                     "connections": []}
            self.state["pcs"][pc_name] = entry
        token = uuid.uuid4().hex
        connection = {"token": token, "phase": "creating", "endpoints": [
            {"container_id": target["Id"], "container_name": target["Name"].lstrip("/"),
             "interface": target_interface, "temporary": "vd" + token[:10] + "a"},
            {"container_id": pc["Id"] if pc else None, "container_name": pc_name,
             "interface": pc_interface, "temporary": "vd" + token[:10] + "p"}]}
        entry["connections"].append(connection)
        self.save()
        try:
            if not pc:
                pc_id = run(["docker", "run", "-d", "--pull=never", "--init", "--network", "none", "--name", pc_name,
                             "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
                             "--sysctl", "net.ipv4.ip_forward=0", "--sysctl", "net.ipv6.conf.all.forwarding=0",
                             "--label", LABEL + ".creator=" + entry["creator"],
                             "--label", "io.route-ovs.role=vpcs", "--entrypoint", "sleep", self.image, "infinity"]).strip()
                entry["container_id"] = pc_id
                connection["endpoints"][1]["container_id"] = pc_id
                self.save()
                pc = self.live(pc_id)
                self.require_free(pc, pc_interface)
            self.create_pair(connection, target, pc)
            connection["phase"] = "ready"
            self.save()
        except (Exception, KeyboardInterrupt) as error:
            try:
                self.disconnect(connection)
                entry["connections"].remove(connection)
                self.save()
                if new_entry:
                    self.finish_entry(entry)
            except (Exception, KeyboardInterrupt) as cleanup:
                connection["phase"] = "cleanup-required"
                if connection not in entry["connections"]:
                    entry["connections"].append(connection)
                self.state["pcs"][pc_name] = entry
                self.save()
                raise TopologyError("创建失败: {}；尚有资源未清理: {}。请执行 --del-vpcs {} {}。".format(
                    error, cleanup, pc_name, pc_interface)) from error
            raise TopologyError("创建失败，已回滚本次操作: {}".format(error)) from error
        print("已直连：{}.{} ↔ {}.{}".format(target["Name"].lstrip("/"), target_interface, pc_name, pc_interface))
        print("{}容器 {}；未配置 IP、网关或 DHCP。".format("复用" if existing else "创建", pc_name))

    def locate(self, connection):
        inventory = self.inventory()
        spaces = [(None, run_json(["ip", "-j", "-d", "link", "show"]))]
        for cid in dict.fromkeys(end["container_id"] for end in connection["endpoints"] if end["container_id"]):
            if cid not in inventory.values():
                continue
            container = self.inspect(cid)
            if container["State"].get("Running"):
                spaces.append((container, self.links(container)))
        found = []
        for index, end in enumerate(connection["endpoints"]):
            alias = "route-ovs:" + connection["token"] + ":" + str(index)
            matches = []
            for container, links in spaces:
                for link in links:
                    marked = link.get("ifalias") == alias
                    initial = (container is None and not link.get("ifalias")
                               and link["ifname"] == end["temporary"] and end.get("ifindex") is not None
                               and link["ifindex"] == end["ifindex"] and link.get("address") == end.get("mac"))
                    if marked or initial:
                        if link.get("linkinfo", {}).get("info_kind") != "veth":
                            raise TopologyError("记录对应的接口已不是 veth，拒绝清理")
                        matches.append((container, link))
            if len(matches) > 1:
                raise TopologyError("接口归属标记重复，拒绝清理")
            found.extend(matches)
        return found

    def disconnect(self, connection):
        found = self.locate(connection)
        if not found:
            return
        if len(found) == 2:
            left, right = found[0][1], found[1][1]
            left_peer = left.get("link_index")
            right_peer = right.get("link_index")
            if left_peer is not None and right_peer is not None and (
                    left_peer != right["ifindex"] or right_peer != left["ifindex"]):
                raise TopologyError("记录中的两个接口不再互为对端，拒绝清理")
        container, link = found[0]
        if container:
            self.require_same_process(container)
            self.root("nsenter", "-t", str(container["State"]["Pid"]), "-n", "ip", "link", "delete", "dev", link["ifname"])
        else:
            self.root("ip", "link", "delete", "dev", link["ifname"])
        if self.locate(connection):
            raise TopologyError("veth 删除后仍有残留接口，保留记录")

    def finish_entry(self, entry):
        if entry["connections"]:
            return
        inventory = self.inventory()
        if entry["owned"] and entry["name"] in inventory:
            current = self.inspect(entry["name"])
            labels = current.get("Config", {}).get("Labels") or {}
            matches = (labels.get(LABEL + ".creator") == entry["creator"] and
                       (not entry["container_id"] or current["Id"] == entry["container_id"]))
            if matches:
                if current["State"].get("Running") and any(link["ifname"] != "lo" for link in self.links(current)):
                    print("保留容器 {}：仍有其他接口；以后可再次执行 --del-vpcs 清理。".format(entry["name"]))
                    return
                run(["docker", "rm", "-f", current["Id"]])
        del self.state["pcs"][entry["name"]]
        self.save()

    def remove(self, name, interface=None):
        if name not in self.state["pcs"]:
            raise TopologyError("当前目录没有该 PC 的连接记录: " + name)
        entry = self.state["pcs"][name]
        chosen = [c for c in entry["connections"] if interface is None or c["endpoints"][1]["interface"] == interface]
        if interface is not None and not chosen:
            raise TopologyError("当前目录没有该 PC 接口的连接记录: " + name + "." + interface)
        for connection in chosen:
            connection["phase"] = "deleting"
            self.save()
            self.disconnect(connection)
            entry["connections"].remove(connection)
            self.save()
        self.finish_entry(entry)
        print("已清理连接：{}{}".format(name, "." + interface if interface else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description="用一对 veth 直连两个容器的空闲接口名")
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--image", default="alpine/vpcs:latest")
    commands = parser.add_subparsers(dest="action", required=True)
    add = commands.add_parser("add")
    for name in ("target", "target_interface", "pc", "pc_interface"):
        add.add_argument(name)
    delete = commands.add_parser("delete")
    delete.add_argument("name")
    delete.add_argument("interface", nargs="?")
    commands.add_parser("delete-all")
    args = parser.parse_args(argv)
    try:
        if args.state_file.is_symlink():
            raise TopologyError("VPCS 记录文件不能是符号链接")
        with args.state_file.with_suffix(".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise TopologyError("已有 VPCS 操作正在执行，请稍后重试")
            manager = Manager(args.state_file, args.image)
            if args.action == "add":
                manager.add(args.target, args.target_interface, args.pc, args.pc_interface)
            else:
                names = [args.name] if args.action == "delete" else list(manager.state["pcs"])
                if names:
                    manager.authorize()
                for name in names:
                    manager.remove(name, args.interface if args.action == "delete" else None)
        return 0
    except (TopologyError, OSError, ValueError, KeyError, TypeError) as error:
        print("错误：{}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
