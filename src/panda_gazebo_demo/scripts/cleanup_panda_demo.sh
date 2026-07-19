#!/usr/bin/env bash
set -u

patterns=(
  'ros2 launch panda_gazebo_demo panda_gazebo.launch.py'
  '/opt/ros/jazzy/lib/moveit_ros_move_group/move_group'
  '/opt/ros/jazzy/lib/robot_state_publisher/robot_state_publisher'
  '/opt/ros/jazzy/lib/ros_gz_bridge/parameter_bridge'
  '/opt/ros/jazzy/lib/rviz2/rviz2.*panda_gazebo_demo'
  'ruby .*gz sim .*table_coke.sdf'
  'gz sim .*table_coke.sdf'
  '^gz sim server$'
  '^gz sim gui$'
)

find_demo_pids()
{
  for pattern in "${patterns[@]}"; do
    pgrep -f -- "$pattern" 2>/dev/null || true
  done | sort -nu
}

find_alive()
{
  local pid

  for pid in "$@"; do
    if kill -0 "$pid" 2>/dev/null; then
      printf '%s\n' "$pid"
    fi
  done
}

mapfile -t pids < <(find_demo_pids)

if ((${#pids[@]} == 0)); then
  echo "No Panda demo processes found."
else
  echo "Found Panda demo processes:"

  for pid in "${pids[@]}"; do
    ps -p "$pid" -o pid=,ppid=,stat=,args= 2>/dev/null || true
  done

  echo "Sending SIGINT..."
  kill -INT "${pids[@]}" 2>/dev/null || true

  for _ in {1..20}; do
    mapfile -t alive < <(find_alive "${pids[@]}")
    ((${#alive[@]} == 0)) && break
    sleep 0.25
  done

  mapfile -t alive < <(find_alive "${pids[@]}")

  if ((${#alive[@]} > 0)); then
    echo "Sending SIGTERM to remaining processes: ${alive[*]}"
    kill -TERM "${alive[@]}" 2>/dev/null || true

    for _ in {1..20}; do
      mapfile -t alive < <(find_alive "${alive[@]}")
      ((${#alive[@]} == 0)) && break
      sleep 0.25
    done
  fi

  mapfile -t alive < <(find_alive "${pids[@]}")

  if ((${#alive[@]} > 0)); then
    echo "Force-stopping stubborn processes: ${alive[*]}"
    kill -KILL "${alive[@]}" 2>/dev/null || true
  fi
fi

# 清除 ROS graph daemon 中可能残留的节点缓存。
if command -v ros2 >/dev/null 2>&1; then
  ros2 daemon stop >/dev/null 2>&1 || true
fi

echo
echo "Remaining matching processes:"
remaining="$(find_demo_pids)"

if [[ -n "$remaining" ]]; then
  while read -r pid; do
    ps -p "$pid" -o pid=,ppid=,stat=,args= 2>/dev/null || true
  done <<< "$remaining"
else
  echo "None."
fi