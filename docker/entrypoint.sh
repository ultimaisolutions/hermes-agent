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

# Apply overrides from signal-ai config and env vars into config.yaml
# (config.yaml is the single source of truth for model and toolset selection)
if [ -f "$INSTALL_DIR/config/signal-ai-config.yaml" ] || [ -n "$HERMES_MODEL" ]; then
    python3 -c "
import yaml, os

cfg_path = os.path.join(os.environ.get('HERMES_HOME', '/opt/data'), 'config.yaml')
override_path = os.path.join(os.environ.get('INSTALL_DIR', '/opt/hermes'), 'config', 'signal-ai-config.yaml')

with open(cfg_path) as f:
    config = yaml.safe_load(f) or {}

changed = False

# Load signal-ai overrides if present
override = {}
if os.path.exists(override_path):
    with open(override_path) as f:
        override = yaml.safe_load(f) or {}

# Apply model: env var takes priority over signal-ai config
desired_model = os.environ.get('HERMES_MODEL') or (override.get('model', {}) or {}).get('default', '')
desired_provider = os.environ.get('HERMES_INFERENCE_PROVIDER') or (override.get('model', {}) or {}).get('provider', '')

if desired_model:
    model_cfg = config.get('model', {})
    if isinstance(model_cfg, str):
        model_cfg = {'default': model_cfg}
    elif not isinstance(model_cfg, dict):
        model_cfg = {}
    if model_cfg.get('default') != desired_model:
        model_cfg['default'] = desired_model
        if desired_provider:
            model_cfg['provider'] = desired_provider
        config['model'] = model_cfg
        changed = True
        print(f'[entrypoint] Model set to: {desired_model} (provider: {desired_provider or \"auto\"})')

# Apply platform_toolsets from signal-ai config
if 'platform_toolsets' in override:
    if config.get('platform_toolsets') != override['platform_toolsets']:
        config['platform_toolsets'] = override['platform_toolsets']
        changed = True
        print(f'[entrypoint] Platform toolsets updated: {override[\"platform_toolsets\"]}')

if changed:
    with open(cfg_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
else:
    print('[entrypoint] Config already up to date')
" 2>&1 || echo "[entrypoint] Warning: failed to apply config overrides"
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
