# Online Dohled pro Home Assistant

Integrace jednou denně stáhne měsíční CSV spotřeby tepla, studené vody a teplé vody z portálu [Online Dohled](https://app.onlinedohled.cz) a zapíše je do statistik Home Assistantu.

Portál nemá API. Přihlášení i export jsou formuláře stránky spotřeby, na které je teplo `Chck0`, studená voda `Chck1` a teplá voda `Chck2`.

## Instalace přes HACS

1. V HACS otevřete **Integrace**, menu vpravo nahoře a **Vlastní repozitáře**.
2. Vložte `https://github.com/pedobry/ha-onlinedohled` a jako kategorii vyberte **Integrace**.
3. Stáhněte **Online Dohled** a restartujte Home Assistant.
4. V Nastavení → Zařízení a služby přidejte integraci **Online Dohled**.
5. Zadejte jméno, heslo a adresu stránky spotřeby z prohlížeče, například `https://app.onlinedohled.cz/GTBC/…/Spotreba03.aspx`.

## Ruční instalace

1. Zkopírujte složku `custom_components/onlinedohled` do `config/custom_components/onlinedohled` v Home Assistantu.
2. Restartujte Home Assistant.
3. V Nastavení → Zařízení a služby přidejte integraci **Online Dohled**.
4. Zadejte jméno, heslo a adresu stránky spotřeby.

Heslo zůstane v konfiguraci integrace. Do chatu ani do protokolu se neposílá.

## Senzory

| Senzor | Jednotka | Význam |
| --- | --- | --- |
| Spotřeba tepla | kWh | Součet uložených měsíců. Portál posílá GJ, grafy energie potřebují kWh. |
| Studená voda | m³ | Součet uložených měsíců. |
| Teplá voda | m³ | Součet uložených měsíců. |

U každého senzoru je atribut `portal_value` s číslem z posledního řádku CSV v jednotce portálu, například GJ. Podle něj jde hodnota porovnat s webem.

CSV obsahuje jen posledních 12 měsíců. Starší měsíce si integrace pamatuje a nikdy je nesníží. Číslo senzoru proto roste od prvního staženého měsíce, není to stav vodoměru od nuly.

Tlačítko **Obnovit spotřeby** stáhne data hned, jinak se stahují jednou za 24 hodin.

## Grafy

V Nastavení → Energie přidejte oba vodní senzory do vody a teplo jako jednotlivé zařízení. První den se spotřeba aktuálního měsíce přičte najednou. Další dny už přibývají denní přírůstky. Uzavřené měsíce se v měsíčním pohledu sečtou do správného měsíce.

Vyžaduje Home Assistant 2026.1 nebo novější a zapnutý recorder.
