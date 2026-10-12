"""Shard checks CUDA driver identity without importing a model library."""

import importlib

import pytest


GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"


@pytest.mark.parametrize("count,uuid,nvml", [(1,GPU,GPU),(0,GPU,GPU),(2,GPU,GPU),(1,"GPU-other",GPU),(1,GPU,"GPU-other")])
def test_exact_selected_device_is_required(monkeypatch,count,uuid,nvml):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.gpu_driver")
    monkeypatch.setattr(mod,"_driver_info",lambda: (count,uuid))
    monkeypatch.setattr(mod,"_nvml_uuid",lambda: nvml)
    if count==1 and uuid==nvml==GPU:
        assert mod.verify_selected_gpu(GPU)["cuda_device_count"] == 1
    else:
        with pytest.raises(ValueError,match="SHARD_GPU_IDENTITY_MISMATCH"):
            mod.verify_selected_gpu(GPU)
