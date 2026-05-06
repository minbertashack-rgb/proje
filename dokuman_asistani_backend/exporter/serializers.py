from rest_framework import serializers


class CheatSheetExportCreateSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField(min_value=1)
    format = serializers.ChoiceField(choices=["md", "pdf", "docx"], default="md")