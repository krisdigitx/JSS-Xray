# Amazon.co.uk HTML price fix

The screenshots showed the underlying issue: Amazon renders prices such as £8.49
with the pence as separate superscript HTML (`£8<sup>49</sup>`). A generic HTML
stripper can turn this into `£849`, while plain-text MIME conversion can produce
`£8 49` or `£8\n49`.

The parser now normalises all of these forms to `£8.49` before extracting prices.

Supported examples:
- `£8<sup>49</sup>` -> £8.49
- `£5<sup>39</sup>` -> £5.39
- `£8 49` -> £8.49
- split-line `£8\n49` -> £8.49
- normal `£8.49` remains unchanged

Existing Gmail messages can be re-read. Existing events remain deduplicated,
while missing order totals and item prices are backfilled.
