# GROBID TEI XML 结构参考

GROBID 产出的 TEI XML 文件遵循 TEI（Text Encoding Initiative）规范，所有元数据位于 `<teiHeader>` 节点内。

## 命名空间

```xml
<TEI xmlns="http://www.tei-c.org/ns/1.0">
```

代码中需使用命名空间前缀：

```python
NS = {"tei": "http://www.tei-c.org/ns/1.0"}
```

## 头部结构

```
<teiHeader>
  <fileDesc>
    <titleStmt>
      <title level="a" type="main">论文标题</title>
      <funder>...</funder>
    </titleStmt>
    <publicationStmt>
      <publisher/>
    </publicationStmt>
    <sourceDesc>
      <biblStruct status="extracted">
        <analytic>
          <author>...</author>          ← 所有作者在这里
          <title level="a">...</title>  ← 标题也在这里（可能重复）
        </analytic>
        <monogr>
          <imprint>
            <date type="published" when="2022">...</date>  ← 出版日期
          </imprint>
        </monogr>
        <idno type="DOI">...</idno>
        <note type="submission">...</note>  ← 投稿/接收日期
      </biblStruct>
    </sourceDesc>
  </fileDesc>
  <profileDesc>
    <abstract>...</abstract>
    <textClass>
      <keywords><term>...</term></keywords>
    </textClass>
  </profileDesc>
</teiHeader>
```

## 作者节点结构

### 模式 1：无内联机构

```xml
<author>
  <persName>
    <forename type="first">Sanjit</forename>
    <surname>Bhat</surname>
  </persName>
  <email>sanjit.bhat@gmail.com</email>
</author>
```

### 模式 2：有内联机构（含地址）

```xml
<author>
  <persName>
    <forename type="first">Saikat</forename>
    <surname>Chakraborty</surname>
  </persName>
  <idno type="ORCID">0000-0002-6889-7171</idno>
  <affiliation key="aff0">
    <orgName type="institution">Columbia University</orgName>
    <address>
      <postCode>10027</postCode>
      <settlement>New York</settlement>
      <region>NY</region>
      <country key="US">USA</country>
    </address>
  </affiliation>
</author>
```

### 模式 3：多机构

```xml
<author>
  <persName>
    <forename type="first">Yutao</forename>
    <surname>Hu</surname>
  </persName>
  <email>yutaohu@hust.edu.cn</email>
  <affiliation key="aff0">
    <orgName type="department">School of Cyber Science and Engineering</orgName>
    <orgName type="institution">Huazhong University of Science and Technology</orgName>
    <address>
      <postCode>430074</postCode>
      <settlement>Wuhan</settlement>
      <country key="CN">China</country>
    </address>
  </affiliation>
  <affiliation key="aff1">
    <orgName type="department">School of Computer Science and Engineering</orgName>
    <orgName type="institution">Nanyang Technological University</orgName>
    <address>
      <settlement>Singapore</settlement>
    </address>
  </affiliation>
</author>
```

## 标题提取优先级

1. `sourceDesc/biblStruct/analytic/title[@level='a']` — 最常见
2. `titleStmt/title[@level='a']` — 备选
3. `titleStmt/title` — 兜底

## 年份提取优先级

1. `monogr/imprint/date[@type='published']/@when` — 最可靠
2. `biblStruct/note` 中匹配 `(19|20)\d{2}` — submission 日期
3. PDF 文件名中的年份模式 — 兜底

## 通讯作者判断

GROBID 通常不会可靠地提供通讯作者标记。`<email>` 只表示邮箱证据，不能单独推出通讯作者。
只有 PDF 首页/脚注中的显式姓名、`corresponding author` 语义、信封/符号与作者的明确位置映射，
或会议 strategy 已验证的等价标记，才能设置 `corresponding=true`；否则保持 `false` 并进入复核。

## 摘要判断

优先使用 `profileDesc/abstract`。使用 pdfplumber 的首页/前两页版面文本验证 `Abstract` 起点，并在
`Keywords`、`CCS Concepts` 或 `Introduction` 处停止。若 TEI 摘要缺失，可使用通过边界检查的 PDF 候选；
TEI 与 PDF 内容冲突时保留两份证据、保留 TEI 结果并写入 `review_queue.csv`。摘要另存为
`conference_year_paper_abstract.csv`，固定列为 `conference,year,title,abstract`。

## 常见噪声来源

| 噪声 | 来源 | 位置 |
|------|------|------|
| IEEE Xplore 水印 | PDF 版权声明被 GROBID 解析 | `note` 节点 |
| 会议信息 | PDF 页眉/页脚 | `note` 或 `orgName` |
| 脚注作者缩写 | GROBID 将脚注中的人名也解析为 author 节点 | `analytic/author` |
| 机构名误识别 | GROBID 将致谢中的机构名解析为 author | `analytic/author` |
| 地址行邮箱残留 | GROBID 将邮箱混入 address/addrLine | `affiliation/address` |
