"""Run the native Cosmos trainer with its official consolidated-checkpoint loader.

The upstream policy entrypoint instantiates random weights, while its DCP
checkpointer deliberately skips .pt files. A released LIBERO .pt must therefore
be loaded before applying FSDP, using Cosmos's own model-loader helper.
"""
from __future__ import annotations

import argparse

import torch.distributed as dist
from megatron.core import parallel_state
from torch.utils.data import DataLoader, DistributedSampler

from cosmos_policy._src.imaginaire.config import load_config
from cosmos_policy._src.imaginaire.lazy_config import instantiate
from cosmos_policy._src.imaginaire.utils import distributed
from cosmos_policy._src.imaginaire.utils.context_managers import data_loader_init, distributed_init, model_init
from cosmos_policy._src.imaginaire.utils.launch import log_reproducible_setup
from cosmos_policy._src.predict2.utils.model_loader import create_model_from_consolidated_checkpoint_with_fsdp


def loader(config, shuffle=True):
    dataset = instantiate(config.dataset)
    sampler = DistributedSampler(dataset=dataset,
        num_replicas=parallel_state.get_data_parallel_world_size(),
        rank=parallel_state.get_data_parallel_rank(), shuffle=shuffle, seed=0)
    return DataLoader(dataset=dataset, sampler=sampler, batch_size=config.batch_size,
        drop_last=config.drop_last, num_workers=config.num_workers,
        persistent_workers=config.persistent_workers, pin_memory=config.pin_memory,
        pin_memory_device=config.pin_memory_device, timeout=config.timeout)


def launch(config, args):
    with distributed_init():
        distributed.init()
    config.validate()
    trainer = config.trainer.type(config)
    log_reproducible_setup(config, args)
    with model_init():
        if str(config.checkpoint.load_path).endswith('.pt'):
            model = create_model_from_consolidated_checkpoint_with_fsdp(config)
        else:
            model = instantiate(config.model)
    # The official loader temporarily switches shard size while loading full tensors.
    config.freeze()
    with data_loader_init():
        train = loader(config.dataloader_train)
        validation = loader(config.dataloader_val, shuffle=False) if config.trainer.run_validation else None
    trainer.train(model, train, validation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('opts', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    config = load_config(args.config, args.opts, enable_one_logger=True)
    try:
        launch(config, args)
    finally:
        if dist.is_initialized():
            dist.destroy_process_group()


if __name__ == '__main__':
    main()
