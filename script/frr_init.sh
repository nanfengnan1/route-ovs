#!/bin/bash

CONTAINER_IMG="quay.io/frrouting/frr:10.0.0"
CONTAINER_FILE=".frr_containers.tmp"

function run_as_root() {
    if [[ "$EUID" -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

function prepare_netns_access() {
    if ! command -v ip >/dev/null 2>&1; then
        echo >&2 "错误：宿主机未安装 iproute2"
        return 1
    fi
    if [[ "$EUID" -ne 0 ]]; then
        if ! command -v sudo >/dev/null 2>&1; then
            echo >&2 "错误：注册或清理 netns 需要 sudo 或 root 权限"
            return 1
        fi
        sudo -v || return 1
    fi
}

# 注册容器已有的网络命名空间，不创建新的网络栈。
function attach_container_netns() {
    local container_name=$1
    local container_pid current_ns named_ns

    if ! container_pid=$(docker inspect --type container -f '{{.State.Pid}}' "$container_name"); then
        return 1
    fi
    if [[ ! "$container_pid" =~ ^[0-9]+$ ]] || [[ "$container_pid" -eq 0 ]]; then
        echo >&2 "错误：容器 ${container_name} 未运行，无法注册 netns"
        return 1
    fi

    current_ns=$(run_as_root stat -Lc '%d:%i' "/proc/${container_pid}/ns/net") || return 1
    if run_as_root test -e "/var/run/netns/${container_name}"; then
        named_ns=$(run_as_root stat -Lc '%d:%i' "/var/run/netns/${container_name}") || return 1
        if [[ "$named_ns" != "$current_ns" ]]; then
            echo >&2 "错误：netns ${container_name} 指向其他网络命名空间，请先核对旧映射"
            return 1
        fi
        echo "netns ${container_name} 已对应当前容器，复用现有映射"
        return 0
    fi

    run_as_root ip netns attach "$container_name" "$container_pid" || return 1
    echo "已注册 netns ${container_name} -> 容器 PID ${container_pid}"
}

# 删除名称前核对归属；移除名称不改变容器内的网络配置。
function detach_container_netns() {
    local container_name=$1
    local container_pid current_ns named_ns

    if ! run_as_root test -e "/var/run/netns/${container_name}"; then
        return 0
    fi
    if ! container_pid=$(docker inspect --type container -f '{{.State.Pid}}' "$container_name"); then
        echo >&2 "错误：无法核对 netns ${container_name} 的归属，保留该名称"
        return 1
    fi
    if [[ ! "$container_pid" =~ ^[0-9]+$ ]] || [[ "$container_pid" -eq 0 ]]; then
        echo >&2 "错误：容器 ${container_name} 未运行，无法核对 netns 归属，请先启动容器或手动处理旧映射"
        return 1
    fi
    current_ns=$(run_as_root stat -Lc '%d:%i' "/proc/${container_pid}/ns/net") || return 1
    named_ns=$(run_as_root stat -Lc '%d:%i' "/var/run/netns/${container_name}") || return 1
    if [[ "$named_ns" != "$current_ns" ]]; then
        echo >&2 "错误：netns ${container_name} 不属于当前容器，保留该名称和容器"
        return 1
    fi
    run_as_root ip netns delete "$container_name"
}

function register_existing_netns() {
    local container
    local status=0
    if [[ ! -s "$CONTAINER_FILE" ]]; then
        echo >&2 "错误：当前目录没有容器记录 ${CONTAINER_FILE}"
        return 1
    fi
    prepare_netns_access || return 1
    while IFS= read -r container; do
        [[ -z "$container" ]] && continue
        attach_container_netns "$container" || status=1
    done < "$CONTAINER_FILE"
    return "$status"
}

# 容器命名规则校验
function validate_container_name() {
    local name="$1"
    if docker ps -a --format '{{.Names}}' | grep -q "^${name}\$"; then
        echo >&2 "错误：容器 ${name} 已存在"
        return 1
    fi
    if run_as_root test -e "/var/run/netns/${name}" || run_as_root test -L "/var/run/netns/${name}"; then
        echo >&2 "错误：netns 名称 ${name} 已被占用，请先核对旧映射"
        return 1
    fi
}

# 核心启动逻辑增强
function start_frr_docker() {
    if [ -z "$1" ] || ! [[ "$1" =~ ^[0-9]+$ ]] || [ "$1" -lt 1 ] || [ "$1" -gt 26 ]; then
        echo >&2 "错误：请输入1-26的整数"
        exit 1
    fi

    local docker_nums=$1
    prepare_netns_access || return 1
    echo "正在启动 ${docker_nums} 个FRR容器..."

    for i in $(seq 1 "$docker_nums"); do
        # 生成A-Z字母命名（兼容不同shell环境）
        local container_name="frr_$(printf "\x$(printf %x $((i + 64)) | tr '[:lower:]' '[:upper:]')")"

        validate_container_name "$container_name" || exit 1

        if ! docker run -d --privileged --net=none --name "$container_name" ${CONTAINER_IMG} >> /dev/null; then
            echo >&2 "错误：启动容器 ${container_name} 失败"
            exit 1
        fi

        # 先记录容器；后续初始化失败时仍可用 -s 清理。
        echo "$container_name" >> "$CONTAINER_FILE" || return 1
        attach_container_netns "$container_name" || return 1
        docker exec "$container_name" sed -i 's/ospfd=no/ospfd=yes/g' /etc/frr/daemons || return 1
        docker exec "$container_name" /usr/lib/frr/watchfrr.sh start ospfd || return 1
    done
    echo "成功启动容器列表：$(tr '\n' ' ' < "$CONTAINER_FILE")"
}

# 使用宿主机 tcpdump，在容器网络命名空间内抓包
function tcpdump_container() {
    local container_name=$1
    local interface_name=$2
    local netns_id
    local tool
    local -a capture_cmd

    for tool in docker nsenter tcpdump; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            echo >&2 "错误：宿主机未安装 ${tool} 或该命令不在 PATH 中"
            return 1
        fi
    done

    if ! netns_id=$(docker inspect --type container -f '{{.State.Pid}}' "$container_name"); then
        echo >&2 "错误：无法查询容器 ${container_name}，请检查容器名和 Docker 访问权限"
        return 1
    fi

    if [[ ! "$netns_id" =~ ^[0-9]+$ ]] || [[ "$netns_id" -eq 0 ]]; then
        echo >&2 "错误：容器 ${container_name} 未运行"
        return 1
    fi

    if ! docker exec "$container_name" ip a show dev "$interface_name" &>/dev/null; then
        echo >&2 "错误：容器 ${container_name} 不存在接口 ${interface_name}"
        return 1
    fi

    capture_cmd=(nsenter -n -t "$netns_id" -- tcpdump -i "$interface_name" -nn)
    if [[ "$EUID" -ne 0 ]]; then
        if ! command -v sudo >/dev/null 2>&1; then
            echo >&2 "错误：进入容器网络命名空间需要 root 权限，请安装 sudo 或使用 root 运行"
            return 1
        fi
        capture_cmd=(sudo "${capture_cmd[@]}")
    fi

    echo "正在监听容器 ${container_name} 的 ${interface_name} 接口，按 Ctrl+C 停止..."
    "${capture_cmd[@]}"
}

# 停止逻辑增强
function stop_all_containers() {
    local container
    local status=0
    local -a remaining=()
    if [[ -f "$CONTAINER_FILE" ]]; then
        prepare_netns_access || return 1
        echo "正在停止容器..."
        while IFS= read -r container; do
            [[ -z "$container" ]] && continue
            if ! detach_container_netns "$container"; then
                remaining+=("$container")
                status=1
                continue
            fi
            if docker inspect "$container" &>/dev/null; then
                echo "- 停止 ${container}"
                if ! docker stop "$container" >/dev/null || ! docker rm "$container" >/dev/null; then
                    remaining+=("$container")
                    status=1
                fi
            else
                echo "- 警告：容器 ${container} 不存在"
            fi
        done < "$CONTAINER_FILE"
        if [[ ${#remaining[@]} -eq 0 ]]; then
            rm -f "$CONTAINER_FILE"
        else
            printf '%s\n' "${remaining[@]}" > "$CONTAINER_FILE"
        fi
    else
        echo "未找到容器记录文件"
    fi
    return "$status"
}

# 帮助菜单优化
function generate_topology() {
    local output_file=$1
    local script_dir
    if ! command -v python3 >/dev/null 2>&1; then
        echo >&2 "错误：生成拓扑需要宿主机安装 python3"
        return 1
    fi
    script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || return 1
    if [[ ! -f "$script_dir/python/frr_topology.py" ]]; then
        echo >&2 "错误：缺少 ${script_dir}/python/frr_topology.py，请将辅助脚本放在 python 子目录"
        return 1
    fi
    python3 "$script_dir/python/frr_topology.py" --containers-file "$CONTAINER_FILE" --output "$output_file"
}

function help_menu() {
    echo "FRR容器集群管理脚本 (兼容Docker 20.10+)"
    echo "用法: $0 [选项]"
    echo "选项:"
    echo "  -n, --number <数量>  启动容器并注册同名 netns（1-26）"
    echo "  -s, --stop           清理对应 netns 名称，停止并删除记录的容器"
    echo "      --netns          为当前目录记录的已有容器补登记 netns"
    echo "  -t, --tcpdump <容器名> <接口名>  监听容器网络流量"
    echo "  -g, --topology <文件.svg>  读取当前容器和 OVS 连接，生成 SVG 拓扑图"
    echo "  -h, --help           显示帮助信息"
    echo "示例: $0 -t frr_A eth1"
    echo "示例: $0 --topology ./topology.svg（或 -g ./topology.svg）"
    echo "拓扑参数须单独使用；需要 python3、dot、docker、ip、ovs-vsctl，OVS 查询可能调用 sudo。"
    echo "抓包使用宿主机 tcpdump；普通用户会调用 sudo，按 Ctrl+C 停止。"
    echo "容器/netns 管理记录保存在当前目录的 ${CONTAINER_FILE}。"
}

# 主函数逻辑优化
function main() {
    local container_num=0
    local number_set=false
    local stop_flag=false
    local netns_flag=false
    local tcpdump_set=false
    local topology_set=false
    local topology_file
    local tcpdump_name
    local parsed_args

    # getopt 为 -t 读取容器名，接口名保留在 -- 后的位置参数中。
    if ! parsed_args=$(getopt -o hn:st:g: --long help,number:,stop,tcpdump:,netns,topology: -n "$0" -- "$@"); then
        exit 1
    fi
    eval set -- "$parsed_args"

    while true; do
        case "$1" in
            -h|--help)    help_menu; exit 0 ;;
            -n|--number)  container_num="$2"; number_set=true; shift 2 ;;
            -s|--stop)    stop_flag=true; shift ;;
            --netns)     netns_flag=true; shift ;;
            -g|--topology)
                if $topology_set; then
                    echo >&2 "错误：-g/--topology 只能指定一次"
                    exit 1
                fi
                topology_set=true
                topology_file="$2"
                shift 2
                ;;
            -t|--tcpdump)
                if $tcpdump_set; then
                    echo >&2 "错误：-t/--tcpdump 只能指定一次"
                    exit 1
                fi
                tcpdump_set=true
                tcpdump_name="$2"
                shift 2
                ;;
            --)           shift; break ;;
            *)            echo >&2 "无效参数：$1"; exit 1 ;;
        esac
    done

    if $topology_set && { $stop_flag || $number_set || $tcpdump_set || $netns_flag; }; then
        echo >&2 "错误：-g/--topology 不能与 -n、-s、-t 或 --netns 同时使用"
        exit 1
    fi
    if $netns_flag && { $stop_flag || $number_set || $tcpdump_set; }; then
        echo >&2 "错误：--netns 不能与 -n、-s 或 -t 同时使用"
        exit 1
    fi
    if $tcpdump_set && { $stop_flag || $number_set; }; then
        echo >&2 "错误：-t 不能与 -n 或 -s 同时使用"
        exit 1
    fi
    if $stop_flag && $number_set; then
        echo >&2 "错误：-n 和 -s 不能同时使用"
        exit 1
    fi

    # 执行核心逻辑
    if $tcpdump_set; then
        if [[ -z "$tcpdump_name" || $# -ne 1 || -z "${1:-}" ]]; then
            echo >&2 "错误：抓包需要一个容器名和一个接口名，例如：$0 -t frr_A eth1"
            exit 1
        fi
        tcpdump_container "$tcpdump_name" "$1"
    elif [[ $# -ne 0 ]]; then
        echo >&2 "错误：多余的位置参数：$*"
        exit 1
    elif $topology_set; then
        if [[ -z "$topology_file" ]]; then
            echo >&2 "错误：请指定 SVG 输出文件，例如：$0 -g ./topology.svg"
            exit 1
        fi
        generate_topology "$topology_file"
    elif $stop_flag; then
        stop_all_containers
    elif $netns_flag; then
        register_existing_netns
    elif $number_set; then
        start_frr_docker "$container_num"
    else
        echo >&2 "错误：必须指定有效参数"
        help_menu
        exit 1
    fi
}

main "$@"
