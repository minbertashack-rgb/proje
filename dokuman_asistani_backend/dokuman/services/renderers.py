from rest_framework.renderers import JSONRenderer

class UTF8JSONRenderer(JSONRenderer):
    # PowerShell'in doğru çözmesi için:
    charset = "utf-8"