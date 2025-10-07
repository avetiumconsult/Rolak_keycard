import platform, subprocess

with open("requirements.txt", "w") as f:
    f.write(f"# Python {platform.python_version()} ({platform.architecture()[0]})\n")
    freeze_output = subprocess.run(["pip", "freeze"], capture_output=True, text=True)
    f.write(freeze_output.stdout)
