#!/usr/bin/env python3
"""Read Docker/OVS state and render the recorded FRR lab as an SVG snapshot.

Uses the Python standard library and the host's Graphviz executable. No network
configuration is changed. OVS metadata comes from ovs-docker's external_ids.
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile


class TopologyError(Exception):
    pass


def run(command, timeout=30, input_text=None):
    try:
        result = subprocess.run(command, input=input_text, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TopologyError("命令执行失败 {}: {}".format(command[0], exc)) from exc
    if result.returncode:
        detail = result.stderr.strip() or "退出码 {}".format(result.returncode)
        raise TopologyError("{}: {}".format(command[0], detail))
    return result.stdout


def run_json(command):
    try:
        return json.loads(run(command))
    except ValueError as exc:
        raise TopologyError("{} 返回了无效 JSON".format(command[0])) from exc


def read_names(path):
    try:
        names = list(dict.fromkeys(line.strip() for line in
                                  path.read_text(encoding="utf-8").splitlines()
                                  if line.strip()))
    except OSError as exc:
        raise TopologyError("无法读取容器记录 {}；请在启动容器时的目录运行: {}".format(path, exc)) from exc
    if not names:
        raise TopologyError("容器记录 {} 为空".format(path))
    for name in names:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
            raise TopologyError("容器记录包含无效名称: {!r}".format(name))
    return names


def ovs_value(value):
    if isinstance(value, list) and len(value) == 2:
        kind, data = value
        if kind == "set":
            return [ovs_value(item) for item in data]
        if kind == "map":
            return {key: ovs_value(item) for key, item in data}
        if kind in ("uuid", "named-uuid"):
            return data
    return value


def decode_ovs(raw):
    """ovs-vsctl prints one JSON object per command, even in one transaction."""
    decoder = json.JSONDecoder()
    tables = []
    try:
        while raw.strip():
            value, end = decoder.raw_decode(raw.lstrip())
            raw = raw.lstrip()[end:]
            tables.append([{key: ovs_value(item) for key, item in
                            zip(value["headings"], row)} for row in value["data"]])
    except (ValueError, KeyError, TypeError) as exc:
        raise TopologyError("无法解析 OVS 数据库返回的 JSON") from exc
    if len(tables) != 3:
        raise TopologyError("OVS 未返回完整的 Bridge、Port、Interface 数据")
    return dict(zip(("bridges", "ports", "interfaces"), tables))


def read_ovs():
    # One read transaction avoids mismatching bridge/port/interface snapshots.
    command = ["ovs-vsctl", "--timeout=5", "--format=json", "list", "Bridge",
               "--", "list", "Port", "--", "list", "Interface"]
    try:
        raw = run(command)
    except TopologyError as initial_error:
        if os.geteuid() == 0 or not shutil.which("sudo"):
            raise TopologyError("无法读取 OVS 拓扑: {}".format(initial_error)) from initial_error
        try:
            raw = run(["sudo", "-n"] + command)
        except TopologyError as sudo_error:
            if not sys.stdin.isatty():
                raise TopologyError(
                    "无法读取 OVS 拓扑（{}）；sudo 也未获授权。"
                    "请在宿主机终端运行本命令并输入 sudo 密码，或先执行 sudo -v。"
                    "未生成或覆盖拓扑图。".format(initial_error)) from sudo_error
            print("读取 OVS 需要 sudo 权限，请完成终端验证。", file=sys.stderr)
            # Inherit the terminal so the password prompt is visible; never read it here.
            if subprocess.run(["sudo", "-v"]).returncode:
                raise TopologyError("sudo 验证失败，未生成或覆盖拓扑图")
            raw = run(["sudo", "-n"] + command)
    return decode_ovs(raw)


def collect(names):
    ovs = read_ovs()
    inspected = run_json(["docker", "inspect", "--type", "container"] + names)
    host_links = run_json(["ip", "-j", "-d", "link", "show"])
    containers = []
    warnings = []
    for item in inspected:
        name = item["Name"].lstrip("/")
        state = item["State"]
        container = {"id": item["Id"], "name": name, "pid": state.get("Pid", 0),
                     "status": state["Status"], "running": state.get("Running", False),
                     "interfaces": [], "netns": "未运行"}
        if container["running"]:
            container["interfaces"] = run_json(
                ["docker", "exec", item["Id"], "ip", "-j", "-d", "address", "show"])
            namespace = run(["docker", "exec", item["Id"], "readlink", "/proc/self/ns/net"]).strip()
            container["netns"] = namespace
            match = re.fullmatch(r"net:\[(\d+)\]", namespace)
            alias = Path("/var/run/netns") / name
            try:
                if match and alias.stat().st_ino == int(match.group(1)):
                    container["netns"] = name + " (" + match.group(1) + ")"
                elif alias.exists():
                    warnings.append(name + " 的同名 netns 与容器不匹配")
            except OSError:
                pass
        containers.append(container)
    # Detect a restart/removal during collection instead of mixing old and new interfaces.
    after = run_json(["docker", "inspect", "--type", "container"] + names)
    before_state = {(c["id"], c["pid"], c["status"]) for c in containers}
    after_state = {(c["Id"], c["State"].get("Pid", 0), c["State"]["Status"]) for c in after}
    if before_state != after_state:
        raise TopologyError("采集期间容器状态发生变化，请重新生成拓扑")
    return {"host": socket.gethostname(),
            "captured_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "containers": containers, "host_links": host_links, "ovs": ovs,
            "warnings": warnings}


def as_list(value):
    # OVS serializes a singleton set as its bare atom.
    return value if isinstance(value, list) else [value]


def scalar(value, default=""):
    values = as_list(value)
    return values[0] if values else default


def vlan_label(port):
    tag = scalar(port.get("tag", []), None)
    mode = scalar(port.get("vlan_mode", [])) or ("access" if tag is not None else "trunk")
    trunks = as_list(port.get("trunks", []))
    detail = "VLAN {}".format(tag) if tag is not None else ""
    if mode != "access":
        detail += ("; " if detail else "") + "trunks: " + (
            ",".join(str(tag) for tag in trunks) if trunks else "all")
    return mode + (" · " + detail if detail else "")


def quote(value):
    # Graphviz double-quoted labels; do not allow names to become DOT syntax.
    return json.dumps(str(value), ensure_ascii=False)


def build_dot(snapshot):
    containers = snapshot["containers"]
    warnings = list(snapshot["warnings"])
    ports = {row["_uuid"]: row for row in snapshot["ovs"]["ports"]}
    interfaces = {row["_uuid"]: row for row in snapshot["ovs"]["interfaces"]}
    host_links = {row["ifname"]: row for row in snapshot["host_links"]}
    lines = ["graph topology {",
             'graph [rankdir=LR, bgcolor="#f5f7fb", pad=0.4, nodesep=0.45, ranksep=1.3,',
             '       fontname="Noto Sans CJK SC", fontsize=18, labelloc=t, compound=true];',
             'node [shape=box, style="rounded,filled", fillcolor="#eaf2ff", color="#a4bddf",',
             '      fontname="Noto Sans CJK SC", fontsize=11, margin="0.16,0.10"];',
             'edge [color="#657b98", fontname="Noto Sans CJK SC", fontsize=9];']
    nodes = {}

    def find_container(ref):
        if not ref:
            return None
        matches = [c for c in containers if ref == c["name"] or ref == c["id"] or
                   (len(ref) >= 12 and c["id"].startswith(ref))]
        return matches[0] if len(matches) == 1 else None

    for index, container in enumerate(containers):
        label = "{} [{}]\nnetns: {}\nPID: {}".format(
            container["name"], container["status"], container["netns"], container["pid"])
        lines.append("subgraph cluster_c{} {{".format(index))
        lines.append('label={}; style="rounded"; color="#cbd6e6";'.format(quote(label)))
        links = [link for link in container["interfaces"] if link.get("link_type") != "loopback"]
        for number, link in enumerate(links):
            node_id = "c{}_i{}".format(index, number)
            nodes[(container["id"], link["ifname"])] = (node_id, link)
            addresses = ["{}/{}".format(a["local"], a["prefixlen"])
                         for a in link.get("addr_info", []) if a.get("scope") == "global"]
            label = "{} [{}]\n{}\n{}".format(link["ifname"], link.get("operstate", "UNKNOWN"),
                                              "\n".join(addresses) or "无全局 IP",
                                              link.get("address", ""))
            if link.get("master"):
                label += "\nmaster: " + str(link["master"])
            color = "#eaf2ff" if "UP" in link.get("flags", []) else "#feecec"
            lines.append('{} [label={}, fillcolor={}];'.format(node_id, quote(label), quote(color)))
        if not links:
            label = "无非 loopback 接口" if container["running"] else "容器未运行，无法读取接口"
            lines.append("c{}_empty [label={}, fillcolor=\"#f0f0f0\"];".format(index, quote(label)))
        lines.append("}")

    bridge_count = 0
    connection_count = 0
    connected_keys = set()
    for bridge in sorted(snapshot["ovs"]["bridges"], key=lambda row: row["name"]):
        rows = []
        for port_id in as_list(bridge.get("ports", [])):
            if port_id not in ports:
                raise TopologyError("OVS 数据缺失 Port {}，请重新采集".format(port_id))
            port = ports[port_id]
            for interface_id in as_list(port.get("interfaces", [])):
                if interface_id not in interfaces:
                    raise TopologyError("OVS 数据缺失 Interface {}，请重新采集".format(interface_id))
                interface = interfaces[interface_id]
                meta = interface.get("external_ids", {})
                rows.append((port, interface, find_container(meta.get("container_id")), meta))
        # Scope the graph to bridges attached to this script's recorded containers.
        if not any(container is not None for _, _, container, _ in rows):
            continue
        bridge_id = "b{}".format(bridge_count)
        bridge_count += 1
        lines.append('{} [label={}, fillcolor="#fff1d6", color="#dbad5b", fontsize=15];'.format(
            bridge_id, quote("OVS Bridge\n" + bridge["name"])))
        for number, (port, interface, container, meta) in enumerate(rows):
            # Skip the bridge's own local interface; it is represented by the bridge node.
            if interface["name"] == bridge["name"] and interface.get("type") == "internal":
                continue
            endpoint = nodes.get((container["id"], meta.get("container_iface"))) if container else None
            if endpoint:
                connected_keys.add((container["id"], meta.get("container_iface")))
            edge_label = "{}\n{}".format(port["name"], vlan_label(port))
            if interface.get("link_state"):
                edge_label += "\nlink: " + str(scalar(interface["link_state"], "unknown"))
            if endpoint:
                node_id, link = endpoint
                peer = host_links.get(interface["name"])
                kind = link.get("linkinfo", {}).get("info_kind")
                if kind == "veth" and (not peer or link.get("link_index") != peer.get("ifindex") or
                                       peer.get("link_index") != link.get("ifindex")):
                    warnings.append("{}/{} 的 OVS 元数据与当前 veth 对端不匹配".format(
                        container["name"], link["ifname"]))
                    edge_label += "\n仅 OVS 记录，对端未核实"
                    style = 'style=dashed, color="#c45538"'
                else:
                    connection_count += 1
                    style = 'style=solid'
            else:
                node_id = "{}_other{}".format(bridge_id, number)
                if container:
                    label = container["name"] + "/" + str(meta.get("container_iface", "?")) + "\n接口未找到"
                    warnings.append(label.replace("\n", "："))
                elif meta.get("container_id"):
                    label = str(meta["container_id"]) + "/" + str(meta.get("container_iface", "?")) + "\n未在容器记录中"
                else:
                    label = "宿主机 / OVS 接口\n" + interface["name"]
                if interface.get("type") == "patch":
                    label += "\npatch peer: " + str(interface.get("options", {}).get("peer", "?"))
                elif interface.get("type") in ("vxlan", "gre", "geneve"):
                    label += "\n{} remote: {}".format(interface["type"], interface.get("options", {}).get("remote_ip", "?"))
                lines.append('{} [label={}, fillcolor="#eeeeee"];'.format(node_id, quote(label)))
                style = 'style=dashed' if container else 'style=solid'
            lines.append('{} -- {} [label={}, {}];'.format(node_id, bridge_id, quote(edge_label), style))

    unmapped = [(container, link) for container in containers for link in container["interfaces"]
                if link.get("linkinfo", {}).get("info_kind") == "veth"
                and (container["id"], link["ifname"]) not in connected_keys]
    for container, link in unmapped:
        warnings.append("{}/{} 未找到 ovs-docker 元数据，未推测连接".format(container["name"], link["ifname"]))
    title = "FRR 容器接口拓扑 · {}\n{}\n{} 个容器 / {} 个 OVS 网桥 / {} 条已核对连接".format(
        snapshot["host"], snapshot["captured_at"], len(containers), bridge_count, connection_count)
    title += "\n接口连接快照；不代表转发可达性或 OSPF 邻接"
    if warnings:
        title += "\n存在 {} 项未核实信息，详见终端警告；虚线表示未核实的 OVS 记录".format(len(warnings))
    lines.append("label={};".format(quote(title)))
    lines.append("}")
    return "\n".join(lines), warnings, bridge_count, connection_count


def render(dot, output):
    """Publish only a successfully rendered SVG; preserve an old file on errors."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".frr-topology-", suffix=".svg",
                                         dir=output.parent, delete=False) as temp:
            temp_path = Path(temp.name)
        run(["dot", "-Tsvg", "-o", str(temp_path)], timeout=60, input_text=dot)
        if temp_path.stat().st_size == 0:
            raise TopologyError("Graphviz 输出为空，未覆盖原文件")
        temp_path.chmod(0o644)
        os.replace(str(temp_path), str(output))
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读采集 FRR 容器 / OVS 连接并生成 SVG")
    parser.add_argument("--containers-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output = args.output.absolute()
        if output.suffix.lower() != ".svg":
            raise TopologyError("输出文件必须以 .svg 结尾")
        if not output.parent.is_dir():
            raise TopologyError("输出目录不存在: {}".format(output.parent))
        if output.is_dir() or output.is_symlink():
            raise TopologyError("输出路径必须是普通文件，不能是目录或符号链接")
        for tool in ("docker", "ovs-vsctl", "ip", "dot"):
            if not shutil.which(tool):
                raise TopologyError("宿主机缺少命令: {}".format(tool))
        names = read_names(args.containers_file)
        snapshot = collect(names)
        dot, warnings, bridges, connections = build_dot(snapshot)
        render(dot, output)
        for warning in warnings:
            print("警告：" + warning, file=sys.stderr)
        print("已生成拓扑图：{}（{} 个容器，{} 个 OVS 网桥，{} 条已核对连接）".format(
            output, len(snapshot["containers"]), bridges, connections))
        return 0
    except (TopologyError, OSError, KeyError, TypeError) as exc:
        print("错误：{}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
