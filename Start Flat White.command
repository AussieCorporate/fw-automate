#!/bin/bash
# Double-click this file to launch the Flat White dashboard.
cd "$(dirname "$0")"
source .venv/bin/activate
open "http://localhost:8500"
flatwhite review
