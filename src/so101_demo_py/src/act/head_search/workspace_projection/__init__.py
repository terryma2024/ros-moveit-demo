"""The workspace projection document phase 6 consumes: the legal pick workspace in the head camera.

`vertical_bounds_px` is "the legal pick workspace projected into the head camera, intersected with the
image safety margin, never back-filled from detection extremes" (design section 7.1). Three things have
to exist before an installed phase can compute it: a **declared** legal pick workspace, a projection of
that workspace into the **sealed** head camera, and the image-space extent the projection produces. The
workspace is declared - `config/act/head-camera-geometry-contract.json` fixes
`workspace_x_m`/`workspace_y_m`/`workspace_z_m` and `workspace_step_m`, and the seal's own
`workspace_matrix.samples` counts the samples that declaration produces - but the projection itself is
retained only as that count and five key samples, so this module is the producer that projects it.

Where every number comes from (nothing here is invented):

* **the points**: the geometry contract's declared workspace box under the seal's own sampling rule -
  both declared edges of each axis, at the three declared heights - is the point set. It is the same rule
  the seal's `workspace_matrix` was built with, and this document records the seal's own sample count
  beside the one it computed, refusing a disagreement rather than projecting a different workspace.
* **the poses**: the bounded plan's stop points that lie inside the sealed `required_search_domain_rad`,
  per sealed anchor, plus each anchor's own start angle when that start is inside the domain. The plan is
  phase 2's `bounded_search_stops`, at the coarse step phase 2's own selection rule chooses (the largest
  generated candidate whose sweep covers the required domain from every anchor - the step phase 2
  receipts and phase 6 accepts). A caller holding that plan may declare it instead; a declared step then
  has to be a generated candidate and to cover the domain, or the pose set would be one no plan of this
  geometry could have, which refuses with `CAL_PROJECTION_POSE_SET_AMBIGUOUS`. Every candidate's
  in-domain stop set is recorded and `poses_are_step_independent` says whether the choice mattered. An
  anchor start outside the required domain is recorded as excluded, never clamped.
* **the camera pose**: `head_camera_geometry.camera_pose_from_seal`, the sealed mount model (the neck
  rotates the mount about the world z axis through the sealed `camera_mount_origin_m`), and the scene
  itself is read through MuJoCo at every projected pose so the sealed model and the model the runtime
  steps have to agree, pose by pose, before a point is projected.
* **the projection**: `head_camera_geometry.project_point`, the seal's own projection, and the same
  convention its scene port feeds it (the columns of the rotation are the camera's world axes). The
  document records the camera pose it used for every pose and the function it used for every point.
* **the extent**: per pose, the smallest and largest projected row, clipped to the image; and the
  headline `top_px`/`bottom_px` is the **union** over the visited poses - the envelope of the legal
  workspace in the image, which contains the row of every legal sample at every visited pose. The
  **intersection** over the poses (the rows every visited pose can produce) and the **aimed band** (every
  sample projected at its own bearing, i.e. the row a horizontally centred sample has) are recorded beside
  it, with whether they cover the aimed band, because the lock rule accepts a detection whose box centre
  is inside the centre deadband, and the fine-correction path can hold the neck between the stops.

Not this document's field: the image safety margin. Phase 6 intersects this projection with
`safety_margin_px` from the camera measurements document, so no margin is read, defaulted or intersected
here.

Nothing here loads a detector, touches a GPU, starts a ROS node or commands motion: the run is
detector-free by construction, the receipt and the document both say so, and the only heavy import
(MuJoCo) happens inside the scene reader. Nothing is written unless the caller passes an explicit
`output_dir` (the producer) or `document_path`.
"""
