"""The production head camera's frozen geometry contract and its seal.

The Head Search gate turns on one question the runtime cannot answer later: does the production head
camera actually see the cup's support geometry at all three anchors, over a neck interval that is
provably safe? The dataset images, the search trajectory and the qualification scenes all inherit
whatever answer this module produces, so the answer is a sealed document rather than a claim.

Two layers live here. The pure layer owns the contract, the projection maths, the required search
domain and every acceptance rule; it never imports MuJoCo. The model layer is a port - the production
`MuJoCoHeadCameraScene` supplies camera poses, safe angles, target points and rendered visibility -
so the rules are testable without a GL context and the same rules run against the real scene at the
coverage-gate boundary.
"""
