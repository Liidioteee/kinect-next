"""Read COM VTable layouts out of the Kinect SDK 2.0 header (``Kinect.h``).

Used by ``test_vtable_layout.py``. Run this file directly on a machine with the
SDK installed to regenerate the checked-in snapshot::

    python tests/kinect_header.py
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).parent / "data" / "kinect_vtables.json"

_SDK_ROOT = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft SDKs" / "Kinect"
_INTERFACE_RE = r'MIDL_INTERFACE\("[0-9A-Fa-f-]+"\)\s+{name} : public IUnknown\s*\{{(.*?)\n    \}};'
_METHOD_RE = re.compile(r"STDMETHODCALLTYPE (\w+)\(")

# Python wrapper classes whose name differs from the SDK interface they wrap.
HEADER_NAMES = {"IKinectSensorNative": "IKinectSensor"}


def find_header() -> Path | None:
    """Return the installed ``Kinect.h``, or ``None`` when the SDK is absent."""
    override = os.environ.get("KINECT_SDK_HEADER")
    if override:
        return Path(override) if Path(override).is_file() else None
    candidates = sorted(_SDK_ROOT.glob("v2.0*/inc/Kinect.h"))
    return candidates[-1] if candidates else None


def parse_vtable(header_text: str, interface: str) -> list[str]:
    """Return ``interface``'s own methods (after ``IUnknown``) in VTable order."""
    match = re.search(_INTERFACE_RE.format(name=re.escape(interface)), header_text, re.S)
    if match is None:
        raise LookupError(f"{interface} is not declared in the header")
    return _METHOD_RE.findall(match.group(1))


def wrapped_interfaces() -> dict[str, type]:
    """Every concrete interface wrapper in :mod:`kinect_next.native.interfaces`."""
    from kinect_next.native import interfaces
    from kinect_next.native.com_base import COMBase

    return {
        HEADER_NAMES.get(name, name): obj
        for name, obj in vars(interfaces).items()
        if isinstance(obj, type) and issubclass(obj, COMBase) and obj._vtable_
    }


def load_snapshot() -> dict[str, list[str]]:
    data: dict[str, list[str]] = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return data


def main() -> None:
    header = find_header()
    if header is None:
        raise SystemExit("Kinect.h not found; install the Kinect for Windows SDK 2.0.")
    text = header.read_text(encoding="latin-1")
    snapshot = {name: parse_vtable(text, name) for name in sorted(wrapped_interfaces())}
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(snapshot)} interface layouts from {header} to {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
