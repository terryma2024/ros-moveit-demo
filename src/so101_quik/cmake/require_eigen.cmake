# Prevent a downstream header consumer from silently using a different Eigen ABI.
find_package(Eigen3 3.4.0 EXACT REQUIRED CONFIG)
