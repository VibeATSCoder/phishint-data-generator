Add-Type -AssemblyName 'System.IO.Compression'
Add-Type -AssemblyName 'System.IO.Compression.FileSystem'

$outputPath = Join-Path $PSScriptRoot "BlueBank_AI_Platform_Report.docx"

# Remove existing file
if (Test-Path $outputPath) { Remove-Item $outputPath -Force }

$tempDir = Join-Path $env:TEMP "docx_build_$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
New-Item -ItemType Directory -Path "$tempDir\_rels" -Force | Out-Null
New-Item -ItemType Directory -Path "$tempDir\word" -Force | Out-Null
New-Item -ItemType Directory -Path "$tempDir\word\_rels" -Force | Out-Null
New-Item -ItemType Directory -Path "$tempDir\word\theme" -Force | Out-Null

# [Content_Types].xml
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
</Types>
'@ | Out-File -FilePath "$tempDir\[Content_Types].xml" -Encoding utf8

# _rels/.rels
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
'@ | Out-File -FilePath "$tempDir\_rels\.rels" -Encoding utf8

# word/_rels/document.xml.rels
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/>
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>
'@ | Out-File -FilePath "$tempDir\word\_rels\document.xml.rels" -Encoding utf8

# word/settings.xml
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
  <w:defaultTabStop w:val="720"/>
  <w:characterSpacingControl w:val="doNotCompress"/>
  <w:compat>
    <w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>
  </w:compat>
</w:settings>
'@ | Out-File -FilePath "$tempDir\word\settings.xml" -Encoding utf8

# word/theme/theme1.xml
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office Theme">
  <a:themeElements>
    <a:clrScheme name="BlueBank">
      <a:dk1><a:srgbClr val="1B2A4A"/></a:dk1>
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk2><a:srgbClr val="2C3E6B"/></a:dk2>
      <a:lt2><a:srgbClr val="F0F4F8"/></a:lt2>
      <a:accent1><a:srgbClr val="1A73E8"/></a:accent1>
      <a:accent2><a:srgbClr val="0D47A1"/></a:accent2>
      <a:accent3><a:srgbClr val="42A5F5"/></a:accent3>
      <a:accent4><a:srgbClr val="1565C0"/></a:accent4>
      <a:accent5><a:srgbClr val="90CAF9"/></a:accent5>
      <a:accent6><a:srgbClr val="0288D1"/></a:accent6>
      <a:hlink><a:srgbClr val="1A73E8"/></a:hlink>
      <a:folHlink><a:srgbClr val="0D47A1"/></a:folHlink>
    </a:clrScheme>
    <a:fontScheme name="BlueBank">
      <a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface="B Nazanin"/></a:majorFont>
      <a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface="B Nazanin"/></a:minorFont>
    </a:fontScheme>
    <a:fmtScheme name="Office">
      <a:fillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:fillStyleLst>
      <a:lnStyleLst>
        <a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
        <a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>
      </a:lnStyleLst>
      <a:effectStyleLst>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
        <a:effectStyle><a:effectLst/></a:effectStyle>
      </a:effectStyleLst>
      <a:bgFillStyleLst>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
        <a:solidFill><a:schemeClr val="phClr"/></a:solidFill>
      </a:bgFillStyleLst>
    </a:fmtScheme>
  </a:themeElements>
</a:theme>
'@ | Out-File -FilePath "$tempDir\word\theme\theme1.xml" -Encoding utf8

# word/numbering.xml
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="decimal"/>
      <w:lvlText w:val="%1."/>
      <w:lvlJc w:val="right"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
      <w:rPr><w:rFonts w:cs="B Nazanin"/></w:rPr>
    </w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="&#x25CF;"/>
      <w:lvlJc w:val="right"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/></w:rPr>
    </w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="2">
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="&#x25CB;"/>
      <w:lvlJc w:val="right"/>
      <w:pPr><w:ind w:left="1080" w:hanging="360"/></w:pPr>
      <w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:hint="default"/></w:rPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
  <w:num w:numId="3"><w:abstractNumId w:val="2"/></w:num>
</w:numbering>
'@ | Out-File -FilePath "$tempDir\word\numbering.xml" -Encoding utf8

# word/styles.xml
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="B Nazanin"/>
        <w:sz w:val="24"/>
        <w:szCs w:val="24"/>
        <w:lang w:val="en-US" w:bidi="fa-IR"/>
      </w:rPr>
    </w:rPrDefault>
    <w:pPrDefault>
      <w:pPr>
        <w:bidi/>
        <w:spacing w:after="120" w:line="288" w:lineRule="auto"/>
        <w:jc w:val="right"/>
      </w:pPr>
    </w:pPrDefault>
  </w:docDefaults>

  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:pPr><w:bidi/><w:jc w:val="right"/></w:pPr>
    <w:rPr>
      <w:rFonts w:cs="B Nazanin"/>
      <w:sz w:val="24"/>
      <w:szCs w:val="24"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:jc w:val="center"/>
      <w:spacing w:before="480" w:after="240"/>
      <w:pBdr>
        <w:bottom w:val="single" w:sz="12" w:space="4" w:color="1A73E8"/>
      </w:pBdr>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="B Titr"/>
      <w:b/><w:bCs/>
      <w:color w:val="1B2A4A"/>
      <w:sz w:val="44"/>
      <w:szCs w:val="44"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="Subtitle">
    <w:name w:val="Subtitle"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:jc w:val="center"/>
      <w:spacing w:before="120" w:after="360"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="B Nazanin"/>
      <w:color w:val="2C3E6B"/>
      <w:sz w:val="28"/>
      <w:szCs w:val="28"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:jc w:val="right"/>
      <w:spacing w:before="360" w:after="160"/>
      <w:keepNext/>
      <w:keepLines/>
      <w:pBdr>
        <w:bottom w:val="single" w:sz="8" w:space="4" w:color="1A73E8"/>
      </w:pBdr>
      <w:shd w:val="clear" w:color="auto" w:fill="EBF3FE"/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="B Titr"/>
      <w:b/><w:bCs/>
      <w:color w:val="1B2A4A"/>
      <w:sz w:val="32"/>
      <w:szCs w:val="32"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:jc w:val="right"/>
      <w:spacing w:before="240" w:after="120"/>
      <w:keepNext/>
      <w:keepLines/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="B Titr"/>
      <w:b/><w:bCs/>
      <w:color w:val="1A73E8"/>
      <w:sz w:val="28"/>
      <w:szCs w:val="28"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:jc w:val="right"/>
      <w:spacing w:before="200" w:after="80"/>
      <w:keepNext/>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="B Nazanin"/>
      <w:b/><w:bCs/>
      <w:color w:val="0D47A1"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="ListBullet">
    <w:name w:val="List Bullet"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:numPr><w:numId w:val="2"/></w:numPr>
      <w:spacing w:after="60"/>
      <w:ind w:left="720" w:hanging="360"/>
    </w:pPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="ListBullet2">
    <w:name w:val="List Bullet 2"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:numPr><w:numId w:val="3"/></w:numPr>
      <w:spacing w:after="60"/>
      <w:ind w:left="1080" w:hanging="360"/>
    </w:pPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="ListNumber">
    <w:name w:val="List Number"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:numPr><w:numId w:val="1"/></w:numPr>
      <w:spacing w:after="60"/>
      <w:ind w:left="720" w:hanging="360"/>
    </w:pPr>
  </w:style>

  <w:style w:type="table" w:styleId="TableGrid">
    <w:name w:val="Table Grid"/>
    <w:tblPr>
      <w:bidiVisual/>
      <w:tblBorders>
        <w:top w:val="single" w:sz="4" w:space="0" w:color="B0BEC5"/>
        <w:left w:val="single" w:sz="4" w:space="0" w:color="B0BEC5"/>
        <w:bottom w:val="single" w:sz="4" w:space="0" w:color="B0BEC5"/>
        <w:right w:val="single" w:sz="4" w:space="0" w:color="B0BEC5"/>
        <w:insideH w:val="single" w:sz="4" w:space="0" w:color="B0BEC5"/>
        <w:insideV w:val="single" w:sz="4" w:space="0" w:color="B0BEC5"/>
      </w:tblBorders>
    </w:tblPr>
  </w:style>

  <w:style w:type="paragraph" w:styleId="InfoBox">
    <w:name w:val="InfoBox"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr>
      <w:bidi/>
      <w:jc w:val="right"/>
      <w:spacing w:before="120" w:after="120"/>
      <w:ind w:left="284" w:right="284"/>
      <w:shd w:val="clear" w:color="auto" w:fill="E3F2FD"/>
      <w:pBdr>
        <w:right w:val="single" w:sz="18" w:space="8" w:color="1A73E8"/>
      </w:pBdr>
    </w:pPr>
    <w:rPr>
      <w:rFonts w:cs="B Nazanin"/>
      <w:color w:val="1B2A4A"/>
      <w:sz w:val="22"/>
      <w:szCs w:val="22"/>
    </w:rPr>
  </w:style>

</w:styles>
'@ | Out-File -FilePath "$tempDir\word\styles.xml" -Encoding utf8

# word/header1.xml
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr>
      <w:bidi/>
      <w:jc w:val="left"/>
      <w:pBdr>
        <w:bottom w:val="single" w:sz="6" w:space="4" w:color="1A73E8"/>
      </w:pBdr>
    </w:pPr>
    <w:r>
      <w:rPr>
        <w:rFonts w:cs="B Nazanin"/>
        <w:color w:val="90A4AE"/>
        <w:sz w:val="18"/>
        <w:szCs w:val="18"/>
      </w:rPr>
      <w:t xml:space="preserve">&#x0628;&#x0644;&#x0648;&#x0628;&#x0627;&#x0646;&#x06A9; | &#x06AF;&#x0632;&#x0627;&#x0631;&#x0634; &#x0642;&#x0627;&#x0628;&#x0644;&#x06CC;&#x062A;&#x200C;&#x0647;&#x0627;&#x06CC; &#x067E;&#x0644;&#x062A;&#x0641;&#x0631;&#x0645; &#x0647;&#x0648;&#x0634; &#x0645;&#x0635;&#x0646;&#x0648;&#x0639;&#x06CC; &#x0645;&#x06A9;&#x0627;&#x0644;&#x0645;&#x0647;&#x200C;&#x0627;&#x06CC;</w:t>
    </w:r>
  </w:p>
</w:hdr>
'@ | Out-File -FilePath "$tempDir\word\header1.xml" -Encoding utf8

# word/footer1.xml
@'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr>
      <w:jc w:val="center"/>
      <w:pBdr>
        <w:top w:val="single" w:sz="4" w:space="4" w:color="B0BEC5"/>
      </w:pBdr>
    </w:pPr>
    <w:r>
      <w:rPr>
        <w:rFonts w:cs="B Nazanin"/>
        <w:color w:val="90A4AE"/>
        <w:sz w:val="18"/>
        <w:szCs w:val="18"/>
      </w:rPr>
      <w:t xml:space="preserve">&#x0645;&#x062D;&#x0631;&#x0645;&#x0627;&#x0646;&#x0647; &#x2014; &#x062A;&#x06CC;&#x0645; &#x0647;&#x0648;&#x0634; &#x0645;&#x0635;&#x0646;&#x0648;&#x0639;&#x06CC; &#x0628;&#x0644;&#x0648;&#x0628;&#x0627;&#x0646;&#x06A9; &#x2014; &#x0635;&#x0641;&#x062D;&#x0647; </w:t>
    </w:r>
    <w:r>
      <w:fldChar w:fldCharType="begin"/>
    </w:r>
    <w:r>
      <w:instrText> PAGE </w:instrText>
    </w:r>
    <w:r>
      <w:fldChar w:fldCharType="separate"/>
    </w:r>
    <w:r>
      <w:rPr>
        <w:color w:val="90A4AE"/>
        <w:sz w:val="18"/>
        <w:szCs w:val="18"/>
      </w:rPr>
      <w:t>1</w:t>
    </w:r>
    <w:r>
      <w:fldChar w:fldCharType="end"/>
    </w:r>
    <w:r>
      <w:rPr>
        <w:rFonts w:cs="B Nazanin"/>
        <w:color w:val="90A4AE"/>
        <w:sz w:val="18"/>
        <w:szCs w:val="18"/>
      </w:rPr>
      <w:t xml:space="preserve"> &#x0627;&#x0632; </w:t>
    </w:r>
    <w:r>
      <w:fldChar w:fldCharType="begin"/>
    </w:r>
    <w:r>
      <w:instrText> NUMPAGES </w:instrText>
    </w:r>
    <w:r>
      <w:fldChar w:fldCharType="separate"/>
    </w:r>
    <w:r>
      <w:rPr>
        <w:color w:val="90A4AE"/>
        <w:sz w:val="18"/>
        <w:szCs w:val="18"/>
      </w:rPr>
      <w:t>1</w:t>
    </w:r>
    <w:r>
      <w:fldChar w:fldCharType="end"/>
    </w:r>
  </w:p>
</w:ftr>
'@ | Out-File -FilePath "$tempDir\word\footer1.xml" -Encoding utf8

Write-Host "Template files created. Building document body..."
