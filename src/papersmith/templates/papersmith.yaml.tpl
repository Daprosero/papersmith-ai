version: "1"
name: {{name_yaml}}
title: {{title_yaml}}
topic: {{topic_yaml}}
venue_target: "unspecified"

skills:
  - paper-ingestion
  - proposal-deliberation
  - proposal-implementation
  - remote-execution
  - kaggle-accounts
  - skill-audit

environment:
  python: ">=3.11"
  node: ">=20.0.0"
  cuda: "12.2"

compute_targets:
  default: {{default_target_yaml}}
  targets:
    local-workstation:
      provider: "local"
      device: "cuda:0"
      max_parallel_jobs: 2
      scratch_dir: ".scratch/runs"

    kaggle-gpu-pool:
      provider: "kaggle"
      account_pool: "default"
      accelerator: "GPU_T4_X2"
      internet_access: true
      max_timeout_hours: 9
      auto_pull_artifacts: true

    slurm-cluster:
      provider: "remote-ssh"
      host: "hpc.university.edu"
      partition: "gpu-a100"
      nodes: 1
      gpus_per_node: 2
      walltime: "12:00:00"

execution_profiles:
  smoke_and_invariants:
    target: "local-workstation"
    entrypoint: "pytest implementations/{paper_slug}/tests/test_invariants.py"
    env_vars:
      PYTHONPATH: "implementations/{paper_slug}/src"
      CUDA_VISIBLE_DEVICES: "0"
    timeout_seconds: 300

  sweep_training:
    target: "kaggle-gpu-pool"
    bootstrap: "skills/remote-execution/assets/runner_bootstrap.py"
    entrypoint: "python implementations/{paper_slug}/src/train.py"
    sharding:
      enabled: true
      strategy: "grid"
      parameter: "--seed"
      values: [42, 1337, 2026, 9999]
      distribute_across_accounts: true
    resources:
      min_ram_gb: 16
      gpu_vram_gb: 16
    artifacts:
      collect:
        - "checkpoints/*.pt"
        - "metrics/*.json"
        - "figures/*.png"
      destination: "kaggle-inbox/{job_id}/"

  benchmark_evaluation:
    target: "kaggle-gpu-pool"
    entrypoint: "papermill implementations/{paper_slug}/nb/benchmark.ipynb kaggle-inbox/{job_id}/benchmark_out.ipynb"
    resources:
      accelerator: "GPU_P100"
    artifacts:
      collect:
        - "kaggle-inbox/{job_id}/benchmark_out.ipynb"
        - "kaggle-inbox/{job_id}/verdict.json"

# The paper-ingestion skill owns this block. The orchestrator intentionally
# leaves its keys opaque while keeping the block in the same workspace file.
paper_ingestion:
  engine: marker
  mode: fast
  strip_references: true
  source_base: guidance
  source_roots: []
