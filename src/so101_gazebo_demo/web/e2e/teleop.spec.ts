import { expect, test } from "@playwright/test";

const hardLimits: Record<string, [number, number]> = { "1": [-1.91986, 1.91986], "2": [-1.74533, 1.74533], "3": [-1.74533, 1.5708], "4": [-1.65806, 1.65806], "5": [-2.79253, 2.79253], "6": [-0.059303612618397, 1.74533] };
const environment = {
  ROS_DOMAIN_ID: "55", ROS_DISTRO: "jazzy", ROS_VERSION: "2", ROS_PYTHON_VERSION: "3",
  ROS_AUTOMATIC_DISCOVERY_RANGE: "SUBNET", AMENT_PREFIX_PATH: "/data/work/ws_moveit/install:/opt/ros/jazzy",
  COLCON_PREFIX_PATH: "/data/work/ws_moveit/install", GZ_PARTITION: "so101_teleop_live_final",
  GZ_CONFIG_PATH: "/opt/ros/jazzy/opt/gz:".repeat(20), GZ_SIM_RESOURCE_PATH: "/opt/ros/jazzy/share",
  GZ_SIM_SYSTEM_PLUGIN_PATH: "/data/work/ws_moveit/install/so101_gazebo_demo/lib:/opt/ros/jazzy/lib",
  PYTHONPATH: "/data/work/ws_moveit/install/so101_gazebo_demo/lib/python3.12/site-packages",
  LD_LIBRARY_PATH: "/data/work/ws_moveit/install/so101_gazebo_demo/lib:/opt/ros/jazzy/lib",
};
const snapshot = { mode: "READY", revision: 9, simulation_session_id: "e2e-session", environment, joints: Object.fromEntries(["1", "2", "3", "4", "5", "6"].map((name) => [name, { position_rad: 0, velocity_rad_s: 0, lower_limit_rad: hardLimits[name][0], upper_limit_rad: hardLimits[name][1] }])), tcp: { frame_id: "world", tcp_frame: "so101_tcp", x_m: 0.1, y_m: 0.2, z_m: 0.3, roll_rad: 0, pitch_rad: 0, yaw_rad: 0 }, moveit_collisions: [], gazebo_contacts: [] };

test("runtime environment is visible, bounded and copyable", async ({ page }) => {
  await page.route("**/snapshot", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(snapshot) }));
  await page.goto("/");
  await expect(page.getByLabel("Connection metadata")).not.toContainText("ROS domain");
  await expect(page.getByLabel("Connection metadata")).not.toContainText("GZ partition");
  await page.getByRole("tab", { name: "Environment" }).click();
  await expect(page.getByRole("table", { name: "Runtime environment" })).toBeVisible();
  await expect(page.getByTitle(`GZ_CONFIG_PATH=${environment.GZ_CONFIG_PATH}`)).toBeVisible();
  await page.evaluate(() => Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: (value: string) => { (window as any).__copiedEnvironment = value; return Promise.resolve(); } } }));
  await page.getByRole("button", { name: "Copy GZ_PARTITION" }).click();
  expect(await page.evaluate(() => (window as any).__copiedEnvironment)).toBe("so101_teleop_live_final");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test("production styles are applied to the operator UI", async ({ page }) => {
  await page.route("**/snapshot", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(snapshot) }));
  await page.goto("/");

  const bodyStyle = await page.locator("body").evaluate((element) => {
    const style = getComputedStyle(element);
    return { backgroundColor: style.backgroundColor, fontFamily: style.fontFamily };
  });
  expect(bodyStyle.backgroundColor).toBe("rgb(2, 6, 23)");
  expect(bodyStyle.fontFamily.toLowerCase()).not.toContain("times new roman");

  const cardStyle = await page.getByText("Joint actual / target", { exact: true }).locator("..").evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundColor: style.backgroundColor,
      borderRadius: style.borderRadius,
      borderStyle: style.borderStyle,
    };
  });
  expect(cardStyle).toEqual({
    backgroundColor: "rgb(15, 23, 42)",
    borderRadius: "12px",
    borderStyle: "solid",
  });

  const inputStyle = await page.getByLabel("joint 1 target").evaluate((element) => {
    const style = getComputedStyle(element);
    return { backgroundColor: style.backgroundColor, borderStyle: style.borderStyle };
  });
  expect(inputStyle).toEqual({ backgroundColor: "rgb(2, 6, 23)", borderStyle: "solid" });
});

test("connection actions stay fixed before changing metadata on a narrow screen", async ({ page }) => {
  let request = 0;
  await page.route("**/snapshot", (route) => {
    request += 1;
    const long = request % 2 === 0;
    route.fulfill({ contentType: "application/json", body: JSON.stringify({
      ...snapshot,
      sequence: request + 100,
      revision: long ? 987654321012345 : 1,
      simulation_session_id: long ? `session-${"metadata-".repeat(30)}` : "s",
    }) });
  });
  await page.setViewportSize({ width: 420, height: 720 });
  await page.goto("/");
  const lease = page.getByRole("button", { name: "Acquire lease" });
  const firstX = (await lease.boundingBox())!.x;
  await expect(page.getByLabel("Connection metadata")).toContainText("987654321012345", { timeout: 4000 });
  const secondX = (await lease.boundingBox())!.x;
  expect(Math.abs(firstX - secondX)).toBeLessThanOrEqual(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
});

test("operator controls preserve targets and send audited command payloads", async ({ page }) => {
  const consoleErrors: string[] = []; const pageErrors: string[] = []; const payloads: Array<{ path: string; body: any }> = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("WebSocket")) consoleErrors.push(message.text()); });
  await page.route("**/snapshot", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(snapshot) }));
  await page.route("**/captures/e2e.png", (route) => route.fulfill({ contentType: "image/png", body: Buffer.from("89504e470d0a1a0a", "hex") }));
  await page.route("**/*", async (route) => {
    if (new URL(route.request().url()).pathname === "/captures/e2e.png") return route.fulfill({ contentType: "image/png", body: Buffer.from("89504e470d0a1a0a", "hex") });
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON(); payloads.push({ path: new URL(route.request().url()).pathname, body });
    const path = new URL(route.request().url()).pathname;
    if (path === "/control/lease") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, layers: { lease_id: "lease-e2e" } }) });
    if (path === "/plan/joints") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, layers: { plan_id: "plan-e2e" } }) });
    if (path === "/gazebo/screenshot") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, data: { url: "/captures/e2e.png" } }) });
    if (path === "/workflow/start") {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, snapshot_revision: 123, data: { workflow: { run_id: "run-e2e", current_state: "WAIT_GRASP_STABLE", next_state: "MICRO_LIFT" } } }) });
    }
    if (path === "/workflow/step") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, snapshot_revision: 124, data: { workflow: { run_id: "run-e2e", current_state: "MICRO_LIFT", next_state: "ATTACH_GAZEBO" } } }) });
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true }) });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "SO-101 Teleop" })).toBeVisible();
  await page.getByRole("button", { name: "Acquire lease" }).click();
  await page.waitForTimeout(500);
  expect(pageErrors).toEqual([]);
  await expect(page.locator('p[aria-live="polite"]')).toContainText("OK");
  await expect(page.getByRole("button", { name: "Lease active" })).toBeVisible();
  await expect.poll(() => payloads.some((entry) => entry.path === "/control/lease")).toBe(true);
  const joint = page.getByLabel("joint 1 target"); await joint.fill("12"); await page.waitForTimeout(1200); await expect(joint).toHaveValue("12");
  await page.getByRole("tab", { name: "Target" }).click();
  const yamlDownload = page.waitForEvent("download"); await page.getByRole("button", { name: "Download Target YAML" }).click(); expect((await yamlDownload).suggestedFilename()).toBe("so101-target.yaml");
  await page.getByRole("tab", { name: "TCP" }).click();
  await page.getByRole("button", { name: "Tool frame" }).click(); await page.getByRole("button", { name: "X +1 mm" }).click();
  await page.getByRole("tab", { name: "Joints" }).click();
  await page.getByRole("button", { name: "Plan Arm" }).click(); await expect(page.getByRole("button", { name: "Execute All" })).toBeEnabled();
  await joint.fill("13"); await expect(page.getByRole("button", { name: "Execute All" })).toBeDisabled(); await expect(page.getByText(/PLAN_STALE_TARGET/).first()).toBeVisible();
  await page.getByRole("tab", { name: "Gazebo" }).click();
  for (const [label, token] of [["Home", "CONFIRM ROBOT_HOME"], ["Repair scene", "CONFIRM SCENE_REPAIR"], ["Reset world / robot", "CONFIRM SIMULATION_RESET"]] as const) { await page.getByRole("button", { name: label }).click(); await page.getByRole("button", { name: `Confirm ${label}` }).click(); await expect.poll(() => payloads.at(-1)?.body.confirmation).toBe(token); }
  await page.getByRole("button", { name: "Capture Gazebo window" }).click(); await expect(page.getByRole("link", { name: "Download latest Gazebo PNG" })).toHaveAttribute("href", "/captures/e2e.png");
  await expect(page.evaluate(async () => (await fetch("/captures/e2e.png")).headers.get("content-type"))).resolves.toContain("image/png");
  await page.getByRole("tab", { name: "Workflow" }).click();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("button", { name: "Starting…" })).toBeDisabled();
  await expect(page.getByText(/WAIT_GRASP_STABLE/)).toBeVisible();
  await page.getByRole("button", { name: "Next Step" }).click();
  await expect.poll(() => payloads.findLast((entry) => entry.path === "/workflow/step")?.body.snapshot_revision).toBe(123);
  await page.getByRole("button", { name: "Reset workflow" }).click(); await page.getByRole("button", { name: "Confirm Reset workflow" }).click(); await expect.poll(() => payloads.at(-1)?.body.confirmation).toBe("CONFIRM WORKFLOW_RESET");
  expect(consoleErrors).toEqual([]);
});

test("Target YAML import clamps every joint to live safe limits and invalidates the arm plan", async ({ page }) => {
  await page.route("**/snapshot", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(snapshot) }));
  await page.route("**/*", (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const path = new URL(route.request().url()).pathname;
    if (path === "/control/lease") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, message: "lease acquired", layers: { lease_id: "lease-yaml" } }) });
    if (path === "/plan/joints") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, message: "plan created", layers: { plan_id: "plan-yaml" } }) });
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, message: "ok" }) });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Acquire lease" }).click();
  await page.getByRole("button", { name: "Plan Arm" }).click();
  await expect(page.getByRole("button", { name: "Execute Arm" })).toBeEnabled();
  await page.getByRole("tab", { name: "Target" }).click();
  await page.getByLabel("Target YAML file").setInputFiles({
    name: "unsafe.yaml",
    mimeType: "application/yaml",
    buffer: Buffer.from(`version: 1\ntarget:\n  step_frame: WORLD\n  joints_rad: {"1": 0, "2": 0, "3": 9, "4": 0, "5": 0, "6": 0}\n  tcp: {frame_id: world, tcp_frame: so101_tcp, x_m: 0.1, y_m: 0.2, z_m: 0.3, roll_rad: 0, pitch_rad: 0, yaw_rad: 0}\n`),
  });
  await page.getByRole("tab", { name: "Joints" }).click();
  await expect(page.getByLabel("joint 3 target")).toHaveValue("89.50021045914973");
  await expect(page.getByText("Joint 3 clamped to 89.50° (0.5° safety margin).")).toBeVisible();
  await expect(page.getByRole("button", { name: "Execute Arm" })).toBeDisabled();
  await expect(page.getByText(/PLAN_STALE_TARGET/)).toBeVisible();
});

test("failed API codes are toasted globally and TCP planning exposes its pending state", async ({ page }) => {
  await page.route("**/snapshot", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(snapshot) }));
  await page.route("**/*", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const path = new URL(route.request().url()).pathname;
    if (path === "/control/lease") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, layers: { lease_id: "lease-toast" } }) });
    if (path === "/plan/tcp") {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "MOVEIT_IK_FAILED_-31", succeeded: false, message: "No IK solution" }) });
    }
    if (path === "/plan/joints") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true, layers: { plan_id: "toast-plan" } }) });
    if (path === "/plans/toast-plan/execute") return route.fulfill({ contentType: "application/json", body: JSON.stringify({ code: "OK", succeeded: true }) });
    if (path === "/gripper/execute") return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ code: "GRIPPER_ACTION_FAILED", succeeded: false, message: "gripper controller rejected target" }) });
    return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "PLAN_STALE_SCENE", succeeded: false, message: "scene changed" }) });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Acquire lease" }).click();
  await page.getByRole("tab", { name: "TCP" }).click();
  await page.getByRole("button", { name: "Plan TCP" }).click();
  await expect(page.getByRole("button", { name: "Planning TCP…" })).toBeDisabled();
  await expect(page.getByText("MOVEIT_IK_FAILED_-31", { exact: true })).toBeVisible();
  await expect(page.getByText("No IK solution", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Joints" }).click();
  await page.getByRole("button", { name: "Plan Arm" }).click();
  await page.getByRole("button", { name: "Execute All" }).click();
  await expect(page.getByText("GRIPPER_ACTION_FAILED", { exact: true })).toBeVisible();
  await expect(page.getByText("gripper controller rejected target", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("PLAN_STALE_SCENE", { exact: true })).toBeVisible();
  await expect(page.getByText("scene changed", { exact: true })).toBeVisible();
});

test("top-level tabs switch accessibly and preserve joint and TCP targets", async ({ page }) => {
  const consoleErrors: string[] = []; const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("WebSocket")) consoleErrors.push(message.text()); });
  await page.route("**/snapshot", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(snapshot) }));
  await page.setViewportSize({ width: 420, height: 720 });
  await page.goto("/");
  const tabs = ["Joints", "TCP", "Collision", "Target", "Gazebo", "Workflow", "Events"];
  await expect(page.getByRole("tab", { name: "Joints" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Joint actual / target" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "TCP Pose6D actual / target" })).toBeHidden();
  const joint = page.getByLabel("joint 1 target");
  await joint.fill("12.5");
  await page.getByRole("tab", { name: "Joints" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "TCP" })).toHaveAttribute("aria-selected", "true");
  const tcpX = page.locator("label").filter({ hasText: /^x_m/ }).locator("input");
  await tcpX.fill("0.321");
  await page.getByRole("button", { name: "Tool frame" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Tool frame" })).toHaveAttribute("aria-pressed", "true");
  for (const tab of tabs.slice(2)) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    await expect(page.getByRole("tab", { name: tab, exact: true })).toHaveAttribute("aria-selected", "true");
  }
  await page.getByRole("tab", { name: "Joints" }).click();
  await expect(page.getByLabel("joint 1 target")).toHaveValue("12.5");
  await page.getByRole("tab", { name: "TCP" }).click();
  await expect(tcpX).toHaveValue("0.321");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  const tabListOverflow = await page.getByRole("tablist").evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth, overflowX: getComputedStyle(element).overflowX, overflowY: getComputedStyle(element).overflowY }));
  expect(tabListOverflow.scroll).toBeGreaterThan(tabListOverflow.client);
  expect(tabListOverflow.overflowX).toBe("auto");
  expect(tabListOverflow.overflowY).toBe("hidden");
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test("collision evidence remains fixed-height and overflow-safe across telemetry extremes", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  let request = 0;
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("console", (message) => { if (message.type() === "error" && !message.text().includes("WebSocket")) consoleErrors.push(message.text()); });
  await page.route("**/snapshot", (route) => {
    request += 1;
    const expanded = request % 2 === 0;
    const suffix = "::collision_name_that_is_intentionally_long".repeat(6);
    const rows = expanded ? Array.from({ length: 20 }, (_, index) => ({
      object_a: `plastic_cup_${index}${suffix}`,
      object_b: `jaw_${index}${suffix}`,
      depth_m: index / 100000,
      source: `telemetry_source_${index}${suffix}`,
    })) : [];
    route.fulfill({ contentType: "application/json", body: JSON.stringify({
      ...snapshot,
      sequence: request + 10,
      source_ages_s: expanded
        ? { joints: 0.000001, tcp: 12345.6789, object: 0.1, gazebo_contacts: 99.999, moveit_collisions: 100, scene: 1.23456 }
        : { joints: 0, tcp: 0, object: 0, gazebo_contacts: 0, moveit_collisions: 0, scene: 0 },
      controllers: { arm_controller: expanded ? "active_with_a_deliberately_long_status_value" : "active", gripper_controller: "inactive" },
      object_pose: snapshot.tcp,
      moveit_collisions: rows,
      gazebo_contacts: rows,
    }) });
  });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await page.getByRole("tab", { name: "Collision" }).click();
  const panel = page.getByLabel("Collision panel");
  await expect(panel).toBeVisible();
  const initialHeight = (await panel.boundingBox())!.height;
  await expect(page.getByLabel("MoveIt evidence pane").getByText("20 evidence rows")).toBeVisible({ timeout: 4000 });
  const expandedHeight = (await panel.boundingBox())!.height;
  expect(Math.abs(expandedHeight - initialHeight)).toBeLessThanOrEqual(2);
  await expect(page.getByRole("heading", { name: "MoveIt collisions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Gazebo contacts" })).toBeVisible();
  for (const label of ["Collision panel", "MoveIt evidence pane", "Gazebo evidence pane"]) {
    const overflow = await page.getByLabel(label).evaluate((element) => ({ client: element.clientWidth, scroll: element.scrollWidth }));
    expect(overflow.scroll).toBeLessThanOrEqual(overflow.client);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
