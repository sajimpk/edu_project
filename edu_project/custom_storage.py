from whitenoise.storage import CompressedManifestStaticFilesStorage

class CustomStaticFilesStorage(CompressedManifestStaticFilesStorage):
    manifest_strict = False
    def delete(self, name):
        try:
            super().delete(name)
        except PermissionError:
            pass
