Jednou denně stáhne spotřebu tepla, studené vody a teplé vody z portálu Online Dohled a zapíše ji do grafů Home Assistantu.

Po instalaci přidejte integraci v **Nastavení → Zařízení a služby**. Do formuláře patří jméno, heslo a adresa stránky spotřeby z prohlížeče, například `https://app.onlinedohled.cz/…/Spotreba03.aspx`.

Vzniknou tři senzory: **Spotřeba tepla** v kWh, **Studená voda** a **Teplá voda** v m³. V **Nastavení → Energie** dejte vodu do vody a teplo jako jednotlivé zařízení.

Číslo senzoru je součet od prvního uloženého měsíce. Atribut `portal_value` ukazuje poslední řádek CSV v jednotce portálu, u tepla v GJ.
