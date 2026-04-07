#!/bin/bash
# Docker entrypoint: bootstrap config files into the mounted volume, then run hermes.
set -e

HERMES_HOME="/opt/data"
INSTALL_DIR="/opt/hermes"

# Create essential directory structure.  Cache and platform directories
# (cache/images, cache/audio, platforms/whatsapp, etc.) are created on
# demand by the application — don't pre-create them here so new installs
# get the consolidated layout from get_hermes_dir().
mkdir -p "$HERMES_HOME"/{cron,sessions,logs,hooks,memories,skills}

# .env
if [ ! -f "$HERMES_HOME/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$HERMES_HOME/.env"
fi

# config.yaml
if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cp "$INSTALL_DIR/cli-config.yaml.example" "$HERMES_HOME/config.yaml"
fi

# Apply model override from HERMES_MODEL env var into config.yaml
# (config.yaml is the single source of truth for model selection)
if [ -n "$HERMES_MODEL" ]; then
    python3 -c "
import yaml, os
cfg_path = os.path.join(os.environ.get('HERMES_HOME', '/opt/data'), 'config.yaml')
with open(cfg_path) as f:
    config = yaml.safe_load(f) or {}
model_cfg = config.get('model', {})
if isinstance(model_cfg, str):
    model_cfg = {'default': model_cfg}
elif not isinstance(model_cfg, dict):
    model_cfg = {}
desired = os.environ['HERMES_MODEL']
provider = os.environ.get('HERMES_INFERENCE_PROVIDER', '')
if model_cfg.get('default') != desired:
    model_cfg['default'] = desired
    if provider:
        model_cfg['provider'] = provider
    config['model'] = model_cfg
    with open(cfg_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f'[entrypoint] Model set to: {desired} (provider: {provider or \"auto\"})')
else:
    print(f'[entrypoint] Model already set to: {desired}')
" 2>&1 || echo "[entrypoint] Warning: failed to apply HERMES_MODEL override"
fi

# SOUL.md
if [ ! -f "$HERMES_HOME/SOUL.md" ]; then
    cp "$INSTALL_DIR/docker/SOUL.md" "$HERMES_HOME/SOUL.md"
fi

# Sync bundled skills (manifest-based so user edits are preserved)
if [ -d "$INSTALL_DIR/skills" ]; then
    python3 "$INSTALL_DIR/tools/skills_sync.py"
fi

exec hermes "$@"
