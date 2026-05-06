# Optional export fonts

Place legally licensed Microsoft YaHei font files here before building the
worker image if PDF export must embed the real YaHei font.

Common Windows font files are:

- `msyh.ttc`
- `msyhbd.ttc`
- `msyhl.ttc`

The Docker image also configures fontconfig aliases so `微软雅黑` and
`Microsoft YaHei` fall back to installed CJK sans fonts when these files are
absent. That fallback keeps Chinese PDF rendering stable, but it is not the
real Microsoft YaHei typeface.
