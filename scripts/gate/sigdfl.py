#!/usr/bin/env python3
"""exec argv with SIGINT/SIGQUIT back at their defaults. A command started with `&` from a non-interactive shell inherits SIGINT=ignored;
python then never installs KeyboardInterrupt, so every test child that waits for SIGINT (launch supervisor cleanup) runs out its 20 s timeout."""
import os, signal, sys
signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGQUIT, signal.SIG_DFL)
os.execvp(sys.argv[1], sys.argv[1:])
