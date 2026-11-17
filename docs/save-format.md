# The `.eu5` save format

How Europa Universalis V binary saves are laid out, as understood by the decoder in
[`backend/app/eu5/`](../backend/app/eu5/). Everything here was worked out from real saves (game
version 1.4.x). Nothing comes from official documentation. The module docstrings are the reference.
Keep them and this page in sync when the format understanding changes.

## Container

```
+--------------------------------+  32 bytes, ASCII
| SAV VV TT XXXXXXXX LLLLLLLL ZZZZZZZZ \n
+--------------------------------+
| metadata (binary tokens)       |  LLLLLLLL bytes
+--------------------------------+
| ZIP archive                    |  starts at the first "PK\x03\x04" after the metadata
|   gamestate      (binary)      |
|   string_lookup  (binary)      |
+--------------------------------+
```

Header fields (hex, no separators in the file), parsed by `parse_header` in
[`container.py`](../backend/app/eu5/container.py):

| Field | Chars | Meaning |
|---|---|---|
| `SAV` | 3 | Magic |
| `version` | 2 | Header version (observed: 3) |
| `save_type` | 2 | Observed: 3 (binary, zipped). Other values not seen yet |
| `unknown` | 8 | Kept as text |
| `metadata_len` | 8 | Length of the metadata block |
| `trailer` | 8 | Kept as text |
| `\n` | 1 | Terminator |

Errors in this layer raise `SaveFormatError` (a `ValueError`). Uploads only validate the header. The full
container is opened by the worker.

## `string_lookup`

A table of strings referenced by index from the token stream
([`string_lookup.py`](../backend/app/eu5/string_lookup.py)):

```
u8   version (observed: 1)
u16  entry count (low 16 bits)
u16  unknown
count x (u16 length + bytes)     UTF-8, cp1252 fallback
```

## Token stream

Both the metadata and `gamestate` are a stream of little-endian **u16 tokens**
([`lexer.py`](../backend/app/eu5/lexer.py)):

| Token | Payload | Meaning |
|---|---|---|
| `0x0001` | – | `=` |
| `0x0003` / `0x0004` | – | `{` / `}` |
| `0x000C` I32 | 4 | signed int (may be a date, see below) |
| `0x0014` U32 | 4 | unsigned int |
| `0x000D` F32 | 4 | IEEE float (not seen in EU5 yet) |
| `0x000E` BOOL | 1 | |
| `0x000F` / `0x0017` | u16 len + bytes | quoted / unquoted string |
| `0x0167` F64 | 8 | i64 fixed point / 100 000 |
| `0x029C` U64, `0x0317` I64 | 8 | |
| `0x0D40` `0x0D43` `0x0D5A` | 1 | index into `string_lookup` (u8) |
| `0x0D3E` `0x0D44` `0x0D5B` | 2 | index into `string_lookup` (u16) |
| `0x0D42` | – | empty string |
| `0x0D47` | – | fixed5 zero |
| `0x0D48`–`0x0D4E` | 1–7 | fixed5 positive: unsigned magnitude of *n* bytes / 100 000 |
| `0x0D4F`–`0x0D55` | 1–7 | fixed5 negative |
| anything else | – | **native name token** |

EU5 defines its own value types in `0x0D3E`–`0x0D5F`. An unknown token in that range is almost
certainly a new type with a payload of unknown size, so the lexer raises `TokenError` instead of
guessing. To add one, see [development.md](development.md#new-value-token).

### Native name tokens

Most keys (and some enum values) are not strings. They are u16 ids whose text is compiled into the game
executable. Names we know go in [`backend/tokens/eu5.txt`](../backend/tokens/eu5.txt) (`<id> <name>`,
hex or decimal, `#` comments). The file is currently empty, so unresolved ids are shown as `"0xNNNN"` and
counted in `unknown_tokens`. `make token-stats` lists candidates with sample values and paths.

Code that needs a native key uses the id directly. `extract.py` does this for the metadata fields
(`META_DATE = 0x06b5`, …) through `tokens.resolve(...)`, so it keeps working once the token is named.

## Values

- **Dates** are I32 **hours since -5000.1.1**, with 365-day years and no leap years
  ([`values.py`](../backend/app/eu5/values.py)). An I32 is rendered as a date (`1444.11.11`) only when it
  falls in years 0..2000 and its key is not in `NOT_DATE_KEYS` (seeds, counters). Pass `dates=False` to
  keep raw hours. The stats layer does this to get sortable values.
- **Fixed-point** values (F64, fixed5) are divided by `FIXED5_SCALE = 100 000`.

## Block → JSON rules

[`parser.py`](../backend/app/eu5/parser.py) turns the stream into dicts and lists:

| Block contents | Result |
|---|---|
| only `key = value` | dict (a repeated key becomes a list of its values) |
| only bare values | list |
| empty | `[]` (`{}` when filtered by `select`) |
| mixed | list where `key = value` entries become `{key: value}` |
| `key = tag { ... }` (e.g. `color = rgb { 1 2 3 }`) | `key: {tag: block}` |
| `{ ... } = value` | key is the block's compact JSON |

Paradox writes a one-element list as a bare value and omits zero/false fields. Consumers must
normalise (`as_list`) and default to 0.

### Partial parsing

Full saves are 25–40 MB. Decoding everything is slow, so the stats layer avoids it:

- `index_top_level(buf)` returns the byte ranges of every top-level key without building objects.
- `parse(memoryview(buf)[s:e], ...)` parses one section.
- `parse(..., select={key: True | {subkey: ...}})` builds only the selected subtrees and skips the
  rest using a precomputed payload-size table.
- `strict=False` closes unbalanced blocks and records messages in `errors` instead of raising.

`parse` and the skip functions are the hot path and are micro-optimised. See the docstring before
changing them.

## Metadata vs gamestate

The metadata block is a small token stream (date, playthrough id and name, game version, …). It is
repeated at the start of `gamestate`, so every unresolved token appears an even number of times in a full
decode (`test_full_decode` relies on this). The stats layer reads only the metadata and these gamestate
sections: `played_country`, `countries` (`tags` + selected `database` entries),
`diplomacy_manager` (only `dependency`), `subunit_manager`, `war_manager` and, when a tracked country
fights a civil war, `provinces` (only `province_definition`).

`diplomacy_manager.dependency` lists subject relations as `{first: overlord id, second: subject id,
named_targets: [{flag: subject_type, target: {type: subject_type, object: <type>}}], start_date, seed}`.
Types seen: `vassal`, `fiefdom`, `dominion`, `appanage`, `tusi`, `taifa`, `maha_samanta`, `tributary`,
`hanseatic_member`, `secessionists`. Subjects can have subjects of their own (3 levels in a 1367 save).
A `secessionists` entry is a rebel province (named after it, e.g. `bornu_province`) listed under the
country that *backs* it, not under the one it rebels against (bornu_province fights KAN but is listed
under KBO).

Wars (`war_manager.database`) have `original_attacker`, `original_attacker_target`, `original_defenders`,
`all` (participants), `start_date` and `end_date` once over. Civil wars set `has_civil_war` (name
`CIVIL_WAR_NAME`; the attacker is a faction country such as `CIVILWAR_FACTION_nobles_estate`, flag
`<TAG>_REVOLT_<n>`); independence wars by rebel provinces or subjects carry a `revolt` key
(`INDEPENDENCE_WAR_NAME`). Factions own their land (`owned_locations`) and their own province objects
(`provinces.database[id].province_definition`); the government keeps its cores on it.

## Decoding a save by hand

```bash
make decode SAVE=backend/autosave.eu5                              # full JSON next to the save
make decode SAVE=backend/autosave.eu5 PARAMS='sections=metadata'
make decode SAVE=backend/autosave.eu5 PARAMS='select=countries,played_country&dates=false'
```

See [api.md](api.md#post-decode) for the parameters.
