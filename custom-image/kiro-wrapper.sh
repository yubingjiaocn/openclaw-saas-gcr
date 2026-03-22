#!/bin/bash
# Redirect HOME to writable PVC path so kiro-cli can write to ~/.kiro/sessions/
export HOME=/home/openclaw/.openclaw
exec kiro-cli "$@"
