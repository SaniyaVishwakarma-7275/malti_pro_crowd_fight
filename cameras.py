# camera.py

# ============================================================
# DVR CAMERA RTSP CONFIGURATION
# ============================================================

CAMERAS = {
    "OFFI_CH01": {
        "name": "Office DVR Ch 01",
        "channel": 1,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=1&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH02": {
        "name": "Office DVR Ch 02",
        "channel": 2,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=2&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH03": {
        "name": "Office DVR Ch 03",
        "channel": 3,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=3&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH04": {
        "name": "Office DVR Ch 04",
        "channel": 4,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=4&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH05": {
        "name": "Office DVR Ch 05",
        "channel": 5,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=5&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH06": {
        "name": "Office DVR Ch 06",
        "channel": 6,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=6&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH07": {
        "name": "Office DVR Ch 07",
        "channel": 7,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=7&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH08": {
        "name": "Office DVR Ch 08",
        "channel": 8,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=8&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH09": {
        "name": "Office DVR Ch 09",
        "channel": 9,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=9&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH10": {
        "name": "Office DVR Ch 10",
        "channel": 10,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=10&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH11": {
        "name": "Office DVR Ch 11",
        "channel": 11,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=11&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH12": {
        "name": "Office DVR Ch 12",
        "channel": 12,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=12&ids=2",
        "mode": "crowd",
        "isActive": True,
    },

    "OFFI_CH13": {
        "name": "Office DVR Ch 13",
        "channel": 13,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=13&ids=2",
        "mode": "fight",
        "isActive": True,
    },

    "OFFI_CH14": {
        "name": "Office DVR Ch 14",
        "channel": 14,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=14&ids=2",
        "mode": "fight",
        "isActive": True,
    },

    "OFFI_CH15": {
        "name": "Office DVR Ch 15",
        "channel": 15,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=15&ids=2",
        "mode": "fight",
        "isActive": True,
    },

    "OFFI_CH16": {
        "name": "Office DVR Ch 16",
        "channel": 16,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=16&ids=2",
        "mode": "fight",
        "isActive": True,
    },

    "OFFI_CH17": {
        "name": "Office DVR Ch 17",
        "channel": 17,
        "rtspUrl": "rtsp://admin:Multi421@122.162.237.4:1030/mode=real&idc=17&ids=2",
        "mode": "crowd",
        "isActive": True,
    },
}


# ============================================================
# CAMERA FUNCTIONS
# ============================================================

def get_camera(camera_code: str):
    """Get one camera configuration."""
    return CAMERAS.get(camera_code)


def get_all_cameras():
    """Return all configured cameras."""
    return [
        {
            "code": code,
            **camera
        }
        for code, camera in CAMERAS.items()
    ]


def get_rtsp_url(camera_code: str):
    """Get RTSP URL for a camera."""
    camera = CAMERAS.get(camera_code)

    if not camera:
        return None

    return camera["rtspUrl"]


def camera_exists(camera_code: str):
    """Check whether camera exists."""
    return camera_code in CAMERAS
