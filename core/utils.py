"""Utility functions for Azure CLI operations."""

import platform
import subprocess


def run_az_command(cmd_args, capture_output=True, text=True, timeout=30):
    """Helper function to run Azure CLI commands with proper Windows support."""
    if platform.system() == "Windows":
        # On Windows, use shell=True to properly handle .cmd files
        cmd = ["az"] + cmd_args
        return subprocess.run(cmd, capture_output=capture_output, text=text, 
                            shell=True, timeout=timeout)
    else:
        # On Unix systems, use the standard approach
        cmd = ["az"] + cmd_args
        return subprocess.run(cmd, capture_output=capture_output, text=text, timeout=timeout)
