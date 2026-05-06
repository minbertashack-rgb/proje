# dokuman_asistani/serializers.py
from rest_framework import serializers
from .models import Dokuman, Vurgu, DokumanParca, ZorYer

def find_all(text: str, sub: str):
    """sub string’inin text içindeki tüm başlangıç indexlerini döndür."""
    if not sub:
        return []
    out = []
    start = 0
    while True:
        idx = text.find(sub, start)
        if idx == -1:
            break
        out.append(idx)
        start = idx + 1
    return out


class VurguSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vurgu
        fields = ["id", "dokuman", "olusturan", "etiket", "baslangic_char", "bitis_char", "renk", "meta", "olusturuldu"]
        read_only_fields = ["id", "dokuman", "olusturan", "olusturuldu"]


class VurguOlusturSerializer(serializers.Serializer):
    etiket = serializers.ChoiceField(choices=[("kanit","kanit"),("cevap","cevap"),("not","not"),("secim","secim")], required=False)
    baslangic_char = serializers.IntegerField(required=False, min_value=0)
    bitis_char = serializers.IntegerField(required=False, min_value=0)
    metin_parcasi = serializers.CharField(required=False, allow_blank=False)
    secim_index = serializers.IntegerField(required=False, min_value=0)  # aynı metin birden çok yerdeyse hangisi?
    renk = serializers.CharField(required=False, allow_blank=True)
    meta = serializers.JSONField(required=False)

    def validate(self, attrs):
        has_span = "baslangic_char" in attrs and "bitis_char" in attrs
        has_snippet = "metin_parcasi" in attrs
        if not has_span and not has_snippet:
            raise serializers.ValidationError("baslangic_char+bitis_char veya metin_parcasi vermelisin.")
        if has_span:
            if attrs["bitis_char"] <= attrs["baslangic_char"]:
                raise serializers.ValidationError("bitis_char baslangic_char'dan büyük olmalı.")
        return attrs

    def create(self, validated_data):
        dokuman: Dokuman = self.context["dokuman"]
        user = self.context["request"].user

        etiket = validated_data.get("etiket", "kanit")
        renk = validated_data.get("renk")
        meta = validated_data.get("meta")

        # 1) direkt span geldiyse
        if "baslangic_char" in validated_data and "bitis_char" in validated_data:
            b = validated_data["baslangic_char"]
            e = validated_data["bitis_char"]
        else:
            # 2) metin_parcasi ile dokümanda bul
            snippet = validated_data["metin_parcasi"]
            hits = find_all(dokuman.metin, snippet)
            if not hits:
                raise serializers.ValidationError({"metin_parcasi": "Bu parça dokümanda bulunamadı."})

            secim_index = validated_data.get("secim_index", 0)
            if secim_index >= len(hits):
                raise serializers.ValidationError({"secim_index": f"Geçersiz. {len(hits)} eşleşme var."})

            b = hits[secim_index]
            e = b + len(snippet)

        if e > len(dokuman.metin):
            raise serializers.ValidationError("Span doküman metnini aşıyor.")

        return Vurgu.objects.create(
            dokuman=dokuman,
            olusturan=user,
            etiket=etiket,
            baslangic_char=b,
            bitis_char=e,
            renk=renk,
            meta=meta,
        )
        
class ZorYerSerializer(serializers.ModelSerializer):
    parca_id = serializers.IntegerField(source="parca.id", read_only=True)
    sira_no = serializers.IntegerField(source="parca.sira_no", read_only=True)
    baslangic_char = serializers.IntegerField(source="parca.baslangic_char", read_only=True)
    bitis_char = serializers.IntegerField(source="parca.bitis_char", read_only=True)
    sayfa_no = serializers.IntegerField(source="parca.sayfa_no", read_only=True)
    baslik = serializers.CharField(source="parca.baslik", read_only=True)

    # UI için istersen snippet döndürelim:
    icerik_kisa = serializers.SerializerMethodField()

    class Meta:
        model = ZorYer
        fields = [
            "parca_id", "sira_no", "baslik",
            "baslangic_char", "bitis_char", "sayfa_no",
            "zorluk_skoru", "metrikler", "guncellendi",
            "icerik_kisa",
        ]

    def get_icerik_kisa(self, obj: ZorYer):
        metin = obj.parca.icerik or ""
        if not metin:
            return ""
        return (metin[:240] + "…") if len(metin) > 240 else metin

class CheatSheetExportCreateSerializer(serializers.Serializer):
    dokuman_id = serializers.IntegerField(min_value=1)
    format = serializers.ChoiceField(choices=["md", "pdf", "docx"], default="md")