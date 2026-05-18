#!/usr/bin/env python3
"""
install.py - Spidergram v3 one-command installer.
Run: python install.py
"""
import os, sys, subprocess, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / "venv"


def run(cmd, check=True):
    print(f"  $ {cmd}")
    return subprocess.run(cmd, shell=True, check=check)


def main():
    print("=" * 55)
    print("  Spidergram v3 - Installer")
    print("=" * 55)

    # 1. Create venv
    if not VENV.exists():
        print("\n[1/7] Creating virtual environment...")
        run(f"{sys.executable} -m venv venv")
    else:
        print("\n[1/7] venv already exists.")

    pip = str(VENV / "bin" / "pip") if os.name != "nt" else str(VENV / "Scripts" / "pip")

    # 2. Upgrade pip
    print("\n[2/7] Upgrading pip...")
    run(f"{pip} install --upgrade pip -q")

    # 3. Install dependencies
    print("\n[3/7] Installing Python dependencies...")
    run(f"{pip} install -r requirements.txt -q")

    # 4. Playwright browser
    print("\n[4/7] Installing Playwright Chromium...")
    python = str(VENV / "bin" / "python") if os.name != "nt" else str(VENV / "Scripts" / "python")
    run(f"{python} -m playwright install chromium", check=False)

    # 5. Ensure __init__.py files
    print("\n[5/7] Verifying package structure...")
    for pkg in ["ui","ui/web_dashboard","ui/chat_interface",
                "core","database","utils","config","agents",
                "pipeline","pipeline/steps","integrations","self_modify"]:
        f = BASE / pkg / "__init__.py"
        if not f.exists():
            f.write_text(f"# {pkg}\n")
            print(f"  Created: {f}")

    # 6. Create directories
    print("\n[6/7] Creating data directories...")
    for d in ["data","data/db","generated_images","logs"]:
        (BASE / d).mkdir(parents=True, exist_ok=True)

    # 7. Setup .env
    print("\n[7/7] Setting up .env...")
    env = BASE / ".env"
    if not env.exists():
        env_example = BASE / ".env.example"
        if env_example.exists():
            shutil.copy(env_example, env)
        else:
            env.write_text(
                "FLASK_SECRET_KEY=change_me_to_a_random_string\n"
                "DASHBOARD_PORT=7111\n"
                "OLLAMA_HOST=http://localhost:11434\n"
                "OLLAMA_MODEL=llama3.2:3b\n"
                "NEWSAPI_KEY=\n"
                "GNEWS_API_KEY=\n"
                "PEXELS_API_KEY=\n"
                "GROK_API_KEY=\n"
                "ELEVENLABS_API_KEY=\n"
                "CLOUDINARY_URL=\n"
            )
        print(f"  .env created at {env}")
        print("  *** Edit .env and add your API keys! ***")
    else:
        print("  .env already exists.")

    print("\n" + "=" * 55)
    print("  Installation complete!")
    print("=" * 55)
    print("\nNext steps:")
    print("  1. Edit .env with your API keys")
    print("  2. Run tests:   python test_and_fix.sh")
    print(f"  3. Start:       {python} main.py --both")
    print("  4. Dashboard:   http://localhost:7111")
    print("\nFor 8GB RAM machines, use light mode:")
    print(f"  {python} main.py --both --light")


if __name__ == "__main__":
    main()
