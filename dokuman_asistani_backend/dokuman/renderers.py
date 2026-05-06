from rest_framework.renderers import JSONRenderer

class UTF8JSONRenderer(JSONRenderer):
    # charset'i DRF otomatik Content-Type'a eklesin
    media_type = "application/json"
    charset = "utf-8"