class BarcodeConverter:
    regex = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
