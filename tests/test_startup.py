from services.startup_service import RUN_KEY, VALUE_NAME, StartupService


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, root, path, *a):
        assert path == RUN_KEY
        return FakeKey()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], 1

    def SetValueEx(self, key, name, _r, _t, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_enable_disable_startup():
    reg = FakeWinreg()
    svc = StartupService(reg)
    assert not svc.is_enabled()
    assert svc.set_enabled(True)[0]
    assert svc.is_enabled() and "main.py" in reg.values[VALUE_NAME] or reg.values[VALUE_NAME].endswith('"')
    assert svc.set_enabled(False)[0]
    assert not svc.is_enabled()
    assert svc.set_enabled(False)[0]  # removing twice is fine


def test_unsupported_platform():
    svc = StartupService(None)
    if not svc.supported:
        ok, msg = svc.set_enabled(True)
        assert not ok and "Windows" in msg
