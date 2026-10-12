"""Read the selected CUDA device through the driver, without loading Torch/YOLO."""

import ctypes
import subprocess
import uuid


def _driver_info():
    class CudaUuid(ctypes.Structure):
        _fields_ = [("bytes",ctypes.c_ubyte*16)]
    library = ctypes.CDLL("libcuda.so.1")
    library.cuInit.argtypes = [ctypes.c_uint]
    library.cuInit.restype = ctypes.c_int
    library.cuDeviceGetCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
    library.cuDeviceGetCount.restype = ctypes.c_int
    library.cuDeviceGetUuid_v2.argtypes = [ctypes.POINTER(CudaUuid),ctypes.c_int]
    library.cuDeviceGetUuid_v2.restype = ctypes.c_int
    count = ctypes.c_int()
    identifier = CudaUuid()
    if library.cuInit(0) != 0 or library.cuDeviceGetCount(ctypes.byref(count)) != 0:
        raise ValueError("SHARD_CUDA_DRIVER_UNAVAILABLE")
    if count.value != 1:
        return count.value,None
    if library.cuDeviceGetUuid_v2(ctypes.byref(identifier),0) != 0:
        raise ValueError("SHARD_CUDA_DRIVER_UNAVAILABLE")
    return count.value,"GPU-"+str(uuid.UUID(bytes=bytes(identifier.bytes)))


def _nvml_uuid():
    return subprocess.run(["nvidia-smi","--query-gpu=uuid","--format=csv,noheader"],
        capture_output=True,text=True,check=True,timeout=5).stdout.strip()


def verify_selected_gpu(gpu_uuid):
    count,actual = _driver_info()
    if count != 1 or actual != gpu_uuid or _nvml_uuid() != gpu_uuid:
        raise ValueError("SHARD_GPU_IDENTITY_MISMATCH")
    return dict(schema_version=1,kind="ACT_SHARD_CUDA_DRIVER",gpu_uuid=actual,cuda_device_count=count)
