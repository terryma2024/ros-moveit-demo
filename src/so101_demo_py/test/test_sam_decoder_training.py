"""Decoder adaptation must not update encoders or reward incorrect masks."""

import importlib

import pytest


@pytest.fixture
def torch():
    # Import at execution time so collection does not initialize thread pools
    # before other tests exercise process creation.
    return pytest.importorskip("torch")


def training_api():
    spec = importlib.util.find_spec("so101_demo.training.sam_decoder_training")
    assert spec is not None, "decoder-only training contract is not implemented"
    return importlib.import_module("so101_demo.training.sam_decoder_training")


def test_optimizer_updates_decoder_only(torch):
    api = training_api()
    model = torch.nn.Module()
    model.vision_encoder = torch.nn.Linear(2, 2)
    model.prompt_encoder = torch.nn.Linear(2, 2)
    model.mask_decoder = torch.nn.Linear(2, 1)
    before = {name: value.detach().clone() for name, value in model.named_parameters()}
    parameters = api.configure_decoder_training(model)
    optimizer = torch.optim.SGD(parameters, lr=0.1)
    value = model.mask_decoder(model.vision_encoder(torch.ones(1, 2)))
    value.sum().backward()
    optimizer.step()
    assert not torch.equal(before["mask_decoder.bias"], model.mask_decoder.bias)
    for name, parameter in model.named_parameters():
        if not name.startswith("mask_decoder."):
            assert torch.equal(parameter, before[name])
            assert parameter.grad is None
            assert not parameter.requires_grad
    assert not model.vision_encoder.training
    assert not model.prompt_encoder.training
    assert model.mask_decoder.training


def test_empty_decoder_rejected(torch):
    with pytest.raises(ValueError, match="DECODER_PARAMETERS_INVALID"):
        training_api().configure_decoder_training(torch.nn.Linear(2, 2))


def test_shared_encoder_decoder_parameter_rejected(torch):
    model = torch.nn.Module()
    model.mask_decoder = torch.nn.Linear(2, 2)
    model.vision_encoder = model.mask_decoder
    with pytest.raises(ValueError, match="DECODER_PARAMETERS_INVALID"):
        training_api().configure_decoder_training(model)


def test_loss_prefers_correct_mask_and_gradients_correct_errors(torch):
    api = training_api()
    truth = torch.tensor([[[[1.0, 0.0], [0.0, 1.0]]]])
    correct = torch.tensor([[[[[8.0, -8.0], [-8.0, 8.0]]]]])
    wrong = (-correct).detach().requires_grad_()
    quality = torch.tensor([[[0.5]]], requires_grad=True)
    loss = api.decoder_loss(wrong, quality, truth)
    assert loss > api.decoder_loss(correct, torch.ones_like(quality), truth)
    loss.backward()
    assert wrong.grad[0, 0, 0, 0, 0] < 0
    assert wrong.grad[0, 0, 0, 0, 1] > 0
    assert quality.grad.item() > 0


def test_all_variants_receive_gradient_at_original_truth_resolution(torch):
    logits = torch.zeros(1, 1, 3, 1, 1, requires_grad=True)
    quality = torch.zeros(1, 1, 3, requires_grad=True)
    truth = torch.ones(1, 1, 2, 2)
    training_api().decoder_loss(logits, quality, truth).backward()
    assert torch.all(logits.grad < 0)
    assert torch.isfinite(logits.grad).all()


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 0.5, -1.0])
def test_invalid_truth_rejected(invalid, torch):
    truth = torch.full((1, 1, 2, 2), invalid)
    with pytest.raises(ValueError, match="TRAINING_TENSORS_INVALID"):
        training_api().decoder_loss(torch.zeros(1, 1, 3, 2, 2), torch.zeros(1, 1, 3), truth)


def test_mismatched_prompt_dimensions_rejected(torch):
    with pytest.raises(ValueError, match="TRAINING_TENSORS_INVALID"):
        training_api().decoder_loss(
            torch.zeros(1, 2, 3, 2, 2), torch.zeros(1, 2, 3), torch.ones(1, 1, 2, 2)
        )
