import CoreGraphics
import Foundation

guard CommandLine.arguments.count == 2, let expectedPID = Int(CommandLine.arguments[1]) else {
  fputs("expected one owner PID\n", stderr)
  exit(2)
}

let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
let raw = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] ?? []
let windows = raw.compactMap { item -> [String: Any]? in
  guard let ownerPID = item[kCGWindowOwnerPID as String] as? Int,
        ownerPID == expectedPID,
        let windowID = item[kCGWindowNumber as String] as? Int else { return nil }
  return [
    "window_id": windowID,
    "owner_pid": ownerPID,
    "owner_name": item[kCGWindowOwnerName as String] as? String ?? "",
    "title": item[kCGWindowName as String] as? String ?? "",
    "onscreen": item[kCGWindowIsOnscreen as String] as? Bool ?? true,
  ]
}
let data = try JSONSerialization.data(withJSONObject: windows, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data("\n".utf8))
