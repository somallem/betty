import torch

from betty.utils import neg_with_none


def neumann(vector, curr, prev):
    """
    Approximate the matrix-vector multiplication with the best response Jacobian by the
    Neumann Series as proposed in
    `Optimizing Millions of Hyperparameters by Implicit Differentiation
    <https://arxiv.org/abs/1911.02590>`_ based on implicit function theorem (IFT). Users may
    specify learning rate (``neumann_alpha``) and unrolling steps (``neumann_iterations``) in
    ``Config``.
    """
    # ! Mabye replace with child.loss by adding self.loss attribute to save computation
    assert len(curr.paths) == 0, 'neumann method is not supported for higher order MLO!'
    config = curr.config
    in_loss = curr.training_step(curr.cur_batch)
    in_grad = torch.autograd.grad(in_loss, curr.trainable_parameters(), create_graph=True)
    v2 = approx_inverse_hvp(vector, in_grad, curr.trainable_parameters(),
                            iterations=config.neumann_iterations,
                            alpha=config.neumann_alpha)
    implicit_grad = torch.autograd.grad(in_grad, prev.trainable_parameters(), grad_outputs=v2)
    implicit_grad = [neg_with_none(ig) for ig in implicit_grad]

    return implicit_grad


def approx_inverse_hvp(v, f, params, iterations=3, alpha=1.):
    p = v
    for _ in range(iterations):
        hvp = torch.autograd.grad(f, params, grad_outputs=v, retain_graph=True)
        v = [v_i - alpha * hvp_i for v_i, hvp_i in zip(v, hvp)]
        p = [v_i + p_i for v_i, p_i in zip(v, p)]

    return [alpha * p_i for p_i in p]
