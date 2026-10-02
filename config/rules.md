<!--
Naming rules. This file is sent as-is (minus this comment) to both model passes: the writer
and the second reader. The fixed sentence itself comes from templates.toml. Every example
below is invented.
-->
## nick

The casual version of their first name, what colleagues would call them. Use a short form only when it is standard and friendly in that person's language (Nicholas -> Nick, Michael -> Mike, Alexander -> Alex, Maximilian -> Max, Christopher -> Chris). With no obvious short form, or when unsure, keep the first name as given, cleaned up (normal capitalisation, no Dr., no middle names). Never invent a diminutive the person could find odd (Andreas stays Andreas, Wouter stays Wouter). Keep the spelling they use themselves: never add accents or umlauts (Joerg stays Joerg, Joao stays Joao) and never drop the ones they use (José stays José, Zoë stays Zoë).

## company

The exact words that go where {company} sits. Two kinds.

### kind "brand"

Only when the company has a distinctive name that sounds natural in the line.

- Keep it short: one word, or the abbreviation people actually use ("Northwind Commerce & Configurators" -> "Northwind", "Kdm Ict Engineering S.r.l." -> "KDM", "Qrs Global" -> "QRS", "Litware Software" -> "Litware", "Tailspin Agency - Ecom Marketing Agency" -> "Tailspin").
- Keep a second word only when it is part of the identity, like "X Consulting" or "X Studio" ("Copper Studios", "Data Orchard", "Hiring Champions": names where the words belong together).
- A distinctive brand word stays a brand even when unfamiliar, as long as it cannot be misread in the line ("Vantoro", "Codexly", "QPT").
- Drop legal forms (GmbH, AG, UG, KG, GmbH & Co. KG, e.K., Ltd, LLC, Inc, Incorporated, Co, Corp, B.V., BV, S.L., SAS, SARL, S.r.l., SA, A/S, AB, ApS, Oy, sp. z o.o.) and taglines after "|" or " - ".
- Write it the way people say and write it in a sentence: domain-style or run-together names become words ("data.harbor" -> "Data Harbor", "Quillmark.io" -> "Quillmark"), shouting or odd capitalisation is fixed ("CLOUDRIDGE AG" -> "Cloudridge"), real acronyms stay upper case ("Kpm Bvt" -> "KPM BVT").

### kind "generic"

"your <what they do> business" (German: the natural casual equivalent with the right possessive, e.g. "deine Beratung", "deine Agentur", "dein Online-Marketing-Business"), where <what they do> is one or two plain words taken only from the data (consulting, online marketing, IT, bookkeeping). Never "your company" or "your business" alone. Use generic whenever the name would sound odd, confusing or awkward in the line:

- it is a description rather than a brand ("Online Marketing", "IT Services & Consulting"), also in another language ("Het Adviesbureau" = "the consultancy" -> "your consulting business"), or the only brand is a descriptive domain (londonbookkeepingservices.example -> "your bookkeeping business");
- the company is named after the lead themselves (Jane Example at "Example Consulting", Max Mustermann at "Mustermann Advisory" -> "your consulting business");
- the short name reads like a common word, a phrase, a person's first name, or something negative or strange when you say it to them ("Been thinking about Panic for a bit", "... about The Framework ...", "... about Emma ...");
- no short form works and the full name is long or clunky.

Pick generic for names that could really be misread or sound odd; a clear, distinctive brand stays a brand.
