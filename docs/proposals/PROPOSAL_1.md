# Operatör iş dağıtımı (F2)

## Gözlem

Operatör panelindeki gerçek dosya kuyruğu öncelik, sınıflandırma güveni, hedef
birim ve F2 ilk personel atamasını gösterebiliyor. Eksik kalan parça, personel
havuzunun panelden yönetilmesi ve manuel yeniden atama.

## Öneri

Bir sonraki kapsamlı geliştirmede mevcut `staff_members` havuzu için ADMIN-only
CRUD ve manuel yeniden atama uçları eklenmeli. Sistem yine aynı birimdeki etkin
kullanıcılardan açık işi en az olanı önermeli; manuel değişiklik ayrı bir
atanabilirlik kaydı olarak kalıcı aksiyon günlüğüne yazılmalı.

## Neden öncelikli

Otomatik ilk atama liste görünümünü gerçek bir iş masasına dönüştürdü. CRUD ve
manuel değişiklik eklendiğinde demo personel havuzu dış bir kimlik sistemi
iddiasına dönüşmeden operasyonel olarak yönetilebilir hâle gelir.
