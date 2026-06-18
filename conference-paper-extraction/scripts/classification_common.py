from __future__ import annotations

import csv
import html
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable


COUNTRY_PATTERN_RULES: list[tuple[str, list[str]]] = [
    ("China", [r"\btsinghua\b", r"\bpeking\b", r"\bfudan\b", r"\bzhejiang\b", r"\bshanghai jiao\b", r"\bshanghai jiaotong\b", r"\bnanjing\b", r"\bwuhan\b", r"\bhuazhong\b", r"\bxidian\b", r"\bbeihang\b", r"\brenmin\b", r"\bchina\b", r"\bchinese academy of sciences\b", r"\bustc\b", r"\buniversity of science and technology of china\b", r"\bbeijing university of posts and telecommunications\b", r"\bshenzhen university\b", r"\bguangzhou university\b", r"\bshanghaitech\b", r"\bsouthern university of science and technology\b", r"\bnankai university\b", r"\bqi-?anxin\b", r"\bcoremail\b", r"\bhuawei\b", r"\balibaba\b", r"\bant group\b", r"\bsangfor\b", r"\bxi'?an jiaotong\b", r"\btencent keen security lab\b", r"\bshandong university\b", r"\bsouthern university of science and technology\b", r"\bnational university of defense technology\b", r"\bsun yat-sen university\b", r"\bbeijing institute of technology\b", r"\bzhongguancun laboratory\b", r"\bzhongguancun lab\b", r"\btianjin university\b", r"\banhui university\b", r"\banhui university of science and technology\b", r"\bxuanwu lab, tencent\b", r"\bhangzhou dianzi university\b", r"\bhunan university\b", r"\bjd explore academy\b", r"\bchinese aeronautical establishment\b", r"\bsoutheast university\b", r"\bchongqing university\b", r"\bbeijing jiaotong university\b", r"\binstitute of information engineering, cas\b", r"\bkey laboratory of cyberspace security defense, institute of information engineering, cas\b", r"\bshanghai university\b", r"\bsouthern university of science and technolog\b", r"\bbeijing university of technology\b", r"\binstitute of information engineering, chinese academy of science\b", r"\bhenan key laboratory of information security\b", r"\bpengcheng laboratory\b", r"\binformation engineering university\b", r"\binstitute for network sciences and cyberspace\b", r"\bacademy of military sciences\b", r"\bbytedance inc\.\b", r"\bbytedance inc\b", r"\bhang zhou city brain co\., ltd\b", r"\bfeiyu tech\b", r"\bshanghai decareer consulting co\., ltd\b", r"\bjinan university\b", r"\bnyu shanghai\b", r"\bbeijing academy of blockchain and edge computing\b", r"\bbeijing electronic science\s*&\s*technology institute\b", r"\bbeijing electronic science and technology institute\b", r"\bstate key laboratory of cryptology\b"]),
    ("China", [r"\bqi an xin\b", r"\bqi anxin\b", r"\bant financial\b", r"\bbaidu security\b", r"\bbaidu x-?lab\b", r"\b360 internet security center\b", r"\bnational research center of parallel computer engineering and technology\b", r"\bstate key laboratory of mathematical engineering and advanced computing\b", r"\bpwnzen\b", r"\bhefei university of technology\b", r"\bharbin institute of technology\b", r"\bharbin institute of technology,? shenzhen\b", r"\bcentral south university\b", r"\bnorthwestern polytechnical university\b", r"\byangzhou university\b", r"\bschool of cyber science and engineering, sichuan university\b", r"\bxi.? an jiaotong university\b"]),
    ("China", [r"\bsichuan university\b", r"\bkeen security lab, tencent\b", r"\btiktok inc\b"]),
    ("Hong Kong", [r"\bhong kong\b", r"\bcuhk\b", r"\bhkust\b", r"\bcity university of hong kong\b", r"\buniversity of macau\b", r"\bcity university of macau\b"]),
    ("Taiwan", [r"\btaiwan\b", r"\bnational taiwan\b", r"\bnational tsing hua\b", r"\bnational chiao tung\b", r"\bacademia sinica\b", r"\bhon hai research institute\b", r"\bnational yang ming chiao tung university\b"]),
    ("Singapore", [r"\bsingapore\b", r"\bnational university of singapore\b", r"\bnanyang technological\b", r"\bsmu\b", r"\ba\*star\b", r"\binfocomm research\b"]),
    ("Singapore", [r"\bkyber network\b"]),
    ("Japan", [r"\bjapan\b", r"\buniversity of tokyo\b", r"\bkyoto\b", r"\bsony\b", r"\bntt\b", r"\bhitachi\b", r"\bpanasonic\b", r"\baist\b", r"\bnational institute of advanced industrial science and technology\b", r"\bnational institute of information and communications technology\b", r"\bnict\b", r"\bkeio university\b", r"\bnagoya university\b", r"\byokohama national university\b", r"\bwaseda university\b"]),
    ("Japan", [r"\bthe university of electro-communications\b"]),
    ("South Korea", [r"\bkorea\b", r"\bkaist\b", r"\bseoul national\b", r"\byonsei\b", r"\bkorea university\b", r"\bsamsung\b", r"\bsoongsil university\b", r"\bkookmin university\b", r"\bunist\b", r"\bewha womans university\b", r"\bkyung hee university\b", r"\bthe affiliated institute of etri, rok\b"]),
    ("South Korea", [r"\bchung-ang university\b", r"\bsungkyunkwan university\b", r"\bsk hynix\b"]),
    ("South Korea", [r"\bs2w inc\.\b", r"\bs2w inc\b"]),
    ("India", [r"\bindia\b", r"\biisc\b", r"\biit bombay\b", r"\biit delhi\b", r"\biit madras\b", r"\bindian institute of technology kharagpur\b", r"\bnit tiruchirappalli\b", r"\bindian institute of technology,? delhi\b", r"\btata institute of fundamental research\b", r"\biit kharagpur\b"]),
    ("India", [r"\bamrita vishwa vidyapeetham\b"]),
    ("Israel", [r"\bisrael\b", r"\bweizmann\b", r"\btechnion\b", r"\btel aviv\b", r"\btel-?aviv university\b", r"\bhebrew university\b", r"\bbar ilan\b", r"\bbar-ilan\b", r"\bben-gurion\b", r"\breichman university\b", r"\buniversity of haifa\b"]),
    ("Canada", [r"\bcanada\b", r"\buniversity of toronto\b", r"\buniversity of waterloo\b", r"\bmcgill\b", r"\buniversity of british columbia\b", r"\bmerit network\b", r"\buniversity of calgary\b", r"\buniversity of guelph\b", r"\bconcordia university\b", r"\bsimon fraser university\b", r"\buniversity of victoria\b"]),
    ("United Kingdom", [r"\buk\b", r"\bunited kingdom\b", r"\bengland\b", r"\buniversity of cambridge\b", r"\buniversity of oxford\b", r"\bimperial college\b", r"\bucl\b", r"\buniversity college london\b", r"\bking'?s college london\b", r"\broyal holloway\b", r"\buniversity of edinburgh\b", r"\buniversity of manchester\b", r"\buniversity of birmingham\b", r"\buniversity of bristol\b", r"\buniversity of glasgow\b", r"\balan turing institute\b", r"\bdurham university\b", r"\blancaster university\b", r"\bnewcastle university\b", r"\bnorthumbria university\b", r"\buniversity of liverpool\b", r"\buniversity of warwick\b", r"\buniversity of surrey\b", r"\bsurrey centre for cyber security\b"]),
    ("United Kingdom", [r"\bscotland\b"]),
    ("United Kingdom", [r"\boxford university\b"]),
    ("United Kingdom", [r"\buniversity of southampton\b"]),
    ("Switzerland", [r"\bswitzerland\b", r"\beth zurich\b", r"\beth z.rich\b", r"\beth zürich\b", r"\beth zuerich\b", r"\bepfl\b", r"\buniversity of zurich\b", r"\buniversity of bern\b", r"\buniversity of geneva\b", r"\bbasel\b", r"\barmasuisse\b", r"\buniversity of lausanne\b"]),
    ("Switzerland", [r"\bstmicroelectronics\b"]),
    ("Switzerland", [r"\beth, zurich\b"]),
    ("Switzerland", [r"\bdfinity\b", r"\bsgs digital trust services\b"]),
    ("Germany", [r"\bgermany\b", r"\bbochum\b", r"\bdarmstadt\b", r"\bkarlsruhe institute\b", r"\bmax planck\b", r"\btechnische universit\b", r"\bludwig maximilian\b", r"\buniversity of stuttgart\b", r"\bcispa\b", r"\bfraunhofer\b", r"\bfreie universität berlin\b", r"\bfreie universitat berlin\b", r"\bhamburg\b", r"\bleibniz university hannover\b", r"\bleibniz universität hannover\b", r"\bleibniz universitat hannover\b", r"\buniversity of würzburg\b", r"\buniversity of wurzburg\b", r"\btechnische universität braunschweig\b", r"\btechnische universitat braunschweig\b", r"\buniversity of duisburg-essen\b", r"\bpaderborn university\b", r"\btechnische universität berlin\b", r"\btechnische universitat berlin\b", r"\btu braunschweig\b", r"\buniversity of lübeck\b", r"\bfriedrich-alexander-universität erlangen-nürnberg\b", r"\bfriedrich-alexander-universitat erlangen-nurnberg\b", r"\bmünster university of applied sciences\b", r"\bmunster university of applied sciences\b", r"\bdatenanfragen\.de\b", r"\bsaarland university\b", r"\brwth aachen university\b", r"\btechnical university of munich\b", r"\btu dortmund university\b", r"\bhasso plattner institute\b", r"\buniversity of potsdam\b", r"\buniversity of osnabrück\b", r"\buniversity of osnabruck\b", r"\bbifold\b", r"\bcarl von ossietzky universität oldenburg\b", r"\bcarl von ossietzky universitat oldenburg\b"]),
    ("Germany", [r"\buniversity of luebeck\b", r"\buniversity luebeck\b", r"\buniversity of bayreuth\b"]),
    ("Germany", [r"\btu dresden\b", r"\bbundeswehr university munich\b", r"\bsap security research\b"]),
    ("France", [r"\bfrance\b", r"\binria\b", r"\bcnrs\b", r"\borange\b", r"\beurecom\b", r"\bcea, list, université paris saclay\b", r"\bcea, list, universite paris saclay\b", r"\buniversité paris saclay\b", r"\buniversite paris saclay\b", r"\bimt atlantique\b", r"\birisa\b"]),
    ("Netherlands", [r"\bnetherlands\b", r"\bdelft\b", r"\beindhoven\b", r"\braadboud\b", r"\bradboud university\b", r"\bvrije universiteit\b", r"\buniversiteit leiden\b", r"\buniversiteit utrecht\b", r"\buniversiteit amsterdam\b", r"\bsidn labs\b", r"\buniversity of twente\b", r"\butrecht university\b", r"\bqusoft\b", r"\bcwi\b", r"\bcentrum wiskunde en informatica\b", r"\bu\. amsterdam\b"]),
    ("Netherlands", [r"\bvu amsterdam\b"]),
    ("Luxembourg", [r"\bluxembourg\b", r"\buniversity of luxembourg\b"]),
    ("Qatar", [r"\bqatar computing research institute\b"]),
    ("Denmark", [r"\bdenmark\b", r"\btechnical university of denmark\b", r"\baarhus university\b"]),
    ("Sweden", [r"\bsweden\b", r"\bkth\b", r"\bchalmers\b", r"\bkarlstad university\b"]),
    ("Sweden", [r"\buppsala university\b"]),
    ("Norway", [r"\bnorway\b", r"\buniversity of oslo\b", r"\bntnu trondheim\b"]),
    ("Finland", [r"\bfinland\b", r"\baalto\b", r"\buniversity of helsinki\b", r"\btampere university\b", r"\bf-secure\b", r"\bmozilla\b"]),
    ("Australia", [r"\baustralia\b", r"\buniversity of melbourne\b", r"\buniversity of sydney\b", r"\bmonash\b", r"\buniversity of queensland\b", r"\buniversity of adelaide\b", r"\buniversity of new south wales\b", r"\bswinburne university of technology\b", r"\bmacquarie university\b", r"\baustralian national university\b", r"\bcsiro'?s data61\b", r"\bdata61\b", r"\buniversity of technology sydney\b", r"\brmit university\b", r"\bwestern sydney university\b", r"\bdefence science and technology group\b", r"\bgriffith university\b", r"\buniversity of wollongong\b"]),
    ("Australia", [r"\batlassian\b"]),
    ("Australia", [r"\bdeakin university\b"]),
    ("New Zealand", [r"\bnew zealand\b", r"\buniversity of auckland\b"]),
    ("Austria", [r"\baustria\b", r"\ba-sit\b", r"\baustrian institute of technology\b", r"\bgraz university of technology\b", r"\bdynatrace research\b", r"\bcomplexity science hub vienna\b", r"\biak\b", r"\biaik\b", r"\btu wien\b", r"\buniversity of innsbruck\b", r"\buniversity of vienna\b", r"\btechnische universität wien\b", r"\btechnische universitat wien\b"]),
    ("Austria", [r"\bsba research\b"]),
    ("Belgium", [r"\bbelgium\b", r"\bku leuven\b", r"\bimec\b", r"\buclouvain\b"]),
    ("Saudi Arabia", [r"\bsaudi arabia\b", r"\bking abdullah university of science and technology\b", r"\bkaust\b", r"\bthuwal\b"]),
    ("Czech Republic", [r"\bbrno university of technology\b"]),
    ("Portugal", [r"\bportugal\b", r"\buniversidade do minho\b", r"\binesc-id\b", r"\binstituto superior técnico\b", r"\binstituto superior tecnico\b", r"\buniversidade de lisboa\b", r"\bnova lincs\b", r"\buniversidade nova de lisboa\b"]),
    ("Portugal", [r"\buniversity of minho\b"]),
    ("Israel", [r"\bben gurion university of the negev\b"]),
    ("Hungary", [r"\beötvös loránd university\b", r"\beotvos lorand university\b"]),
    ("Greece", [r"\bnational technical university of athens\b"]),
    ("Turkey", [r"\btobb university of economics and technology\b"]),
    ("Ireland", [r"\bireland\b"]),
    ("Italy", [r"\bitaly\b", r"\buniversity of trento\b", r"\buniversity of padua\b", r"\buniversità ca' foscari venezia\b", r"\buniversita ca' foscari venezia\b", r"\bsapienza university of rome\b", r"\blink campus university of rome\b"]),
    ("Italy", [r"\buniversity of padova\b", r"\bscuola superiore sant'?anna\b"]),
    ("Spain", [r"\bspain\b", r"\bimdea software institute\b", r"\bimdea networks institute\b", r"\buniversidad carlos iii de madrid\b", r"\buniversidad politécnica de madrid\b", r"\buniversidad politecnica de madrid\b"]),
    ("Spain", [r"\bimdea networks\b"]),
    ("Thailand", [r"\bthailand\b", r"\bprince of songkla university\b"]),
    ("Spain", [r"\bitefi\b", r"\bcsic\b"]),
    ("Egypt", [r"\balexandria university\b"]),
    ("Estonia", [r"\bestonia\b", r"\buniversity of tartu\b", r"\bsoftware technology and applications competence center\b"]),
    ("Romania", [r"\buniv\.? politehnica bucharest\b"]),
    ("Italy", [r"\buniversity of brescia\b"]),
]

US_PATTERN_RULES: list[str] = [
    r"\bindiana university bloomington\b",
    r"\bbinghamton university\b",
    r"\bclemson university\b",
    r"\bdartmouth college\b",
    r"\bflorida state university\b",
    r"\biowa state university\b",
    r"\bnew jersey institute of technology\b",
    r"\blehigh university\b",
    r"\bmichigan state university\b",
    r"\bmichigan technological\b",
    r"\bpennsylvania state university\b",
    r"\bgeorgetown law\b",
    r"\bsanta clara university\b",
    r"\bakamai\b",
    r"\bcisco\b",
    r"\bcisco talos\b",
    r"\bibm t\.j\. watson\b",
    r"\bicann\b",
    r"\bduckduckgo\b",
    r"\bmassmutual\b",
    r"\boracle\b",
    r"\bred hat\b",
    r"\braytheon\b",
    r"\bperaton labs\b",
    r"\brivos\b",
    r"\bkentik\b",
    r"\bnorton research group\b",
    r"\buniversity of chicago\b",
    r"\buc riverside\b",
    r"\buniversity of california,? riverside\b",
    r"\buniversity of vermont\b",
    r"\buniversity of rochester\b",
    r"\brochester institute of technology\b",
    r"\bwilliam\s*&\s*mary\b",
    r"\bwilliam and mary\b",
    r"\bwilliam\s*&\s*mary\b",
    r"\badobe research\b",
    r"\btexas advanced computing center\b",
    r"\btrustwave\b",
    r"\btower research\b",
    r"\btufts university\b",
    r"\bnxp semiconductors\b",
    r"\bwashington university in st\. louis\b",
    r"\bgeorgetown university\b",
    r"\btemple university\b",
    r"\bbrigham young university\b",
    r"\buniversity of central florida\b",
    r"\bflorida international university\b",
    r"\bfiu\b",
    r"\bnetapp\b",
    r"\bgalois\b",
    r"\bgalois, inc\.\b",
    r"\bj\.p\. morgan\b",
    r"\bcyber-physical systems security lab, florida international university\b",
    r"\buniversity of louisiana at lafayette\b",
    r"\buniversity at buffalo\b",
    r"\bvirginia commonwealth university\b",
    r"\bvmware research\b",
    r"\billinois institute of technology\b",
    r"\bcal poly, san luis obispo\b",
    r"\bbrave software\b",
    r"\btulane university\b",
    r"\buniversity of wyoming\b",
    r"\bfordham university\b",
    r"\bgeorgia state university\b",
    r"\bindiana university\b",
    r"\bindiana university bloomington\b",
    r"\buniversity of denver\b",
    r"\bvanderbilt university\b",
    r"\bvirginia polytechnic institute and state university\b",
    r"\bvirginia polytechnic institute & state university\b",
    r"\btexas tech university\b",
    r"\buniversity of georgia\b",
    r"\buniversity of louisville\b",
    r"\buniversity of north texas\b",
    r"\buniversity of south florida\b",
    r"\buniversity of virginia\b",
    r"\buniversity of vriginia\b",
    r"\bwichita state university\b",
    r"\bflorida atlantic university\b",
    r"\buniversity of texas at dallas\b",
    r"\but dallas\b",
    r"\bfisk university\b",
    r"\bfacebook\b",
    r"\bpalo alto networks\b",
    r"\bpaypal\b",
    r"\bbloomberg\b",
    r"\bgrammatech\b",
    r"\bbouncer technologies\b",
    r"\bicij\b",
    r"\binternational computer science institute\b",
    r"\bkryptowire\b",
    r"\bsegment\b",
    r"\bshape security\b",
    r"\bsimons institute\b",
    r"\bnortonlifelock\b",
    r"\bprivate machines\b",
    r"\bunc charlotte\b",
    r"\btrail of bits\b",
    r"\bsyracuse university\b",
    r"\blouisiana state university\b",
    r"\bhendrix college\b",
    r"\bappcensus\b",
    r"\bwesleyan university\b",
    r"\bsaint louis university\b",
    r"\bnc state university\b",
    r"\buniversity of new hampshire\b",
    r"\bdepaul university\b",
    r"\buc san diego health\b",
    r"\bschool of computing, depaul university\b",
    r"\bnec laboratories america\b",
]

COUNTRY_PATTERN_RULES.extend(
    [
        ("Turkey", [r"\bturkiye\b", r"\bsabanci university\b", r"\bbilkent university\b"]),
        ("United Arab Emirates", [r"\btechnology innovation institute\b", r"\babu dhabi\b", r"\buae\b", r"\bunited arab emirates\b"]),
        ("France", [r"\buniversit[ée] de clermont auvergne\b", r"\buniversite de clermont auvergne\b", r"\blimos\b", r"\blisite\b", r"\bisep\b", r"\biriguard\b", r"\buniversit[ée] claude bernard lyon 1\b", r"\blaboratoire jean kuntzmann\b", r"\binstitut de math[ée]matiques de jussieu\b", r"\bcy cergy paris\b", r"\buniversit[ée] de picardie jules verne\b", r"\binstitut de recherche math[ée]matique de rennes\b", r"\bcr[ée]dit agricole\b", r"\binstitut input\b"]),
        ("Belgium", [r"\belen\b", r"\bswift\b", r"\bsociety for worldwide interbank financial telecommunication\b"]),
        ("Germany", [r"\brobert bosch\b", r"\bfederal office for information security\b", r"\brptu kaiserslautern\b", r"\bkaiserslautern-landau\b", r"\buniversity of g[öo]ttingen\b", r"\bmax-planck-institut\b", r"\bfriedrich alexander universit\b", r"\bfriedrich-alexander-universit\b"]),
        ("China", [r"\bguizhou normal university\b", r"\bjiangxi university of finance and economics\b", r"\bsklp\b", r"\binstitute of computing technology, cas\b", r"\bshanghai pudong institute\b", r"\bshangdong agriculture\b", r"\bshandong agriculture\b", r"\bcloud inspur\b", r"\bcrrc zhuzhou\b", r"\btengen intelligence\b", r"\brealai\b", r"\boppo\b"]),
        ("Japan", [r"\bibarki university\b", r"\bibaraki university\b", r"\buniversity of electro-communications\b", r"\buniversity of tsukuba\b", r"\bkddi research\b", r"\bmediatek\b"]),
        ("South Korea", [r"\bcryptolab\b", r"\bcryptolab\. inc\b", r"\bseoul medical center\b"]),
        ("Switzerland", [r"\bfhnw university\b", r"\bfhnw university of applied sciences\b"]),
        ("Norway", [r"\bntnu - norwegian university of science and technology\b"]),
        ("Brazil", [r"\bunicamp\b", r"\buniversity of campinas\b", r"\bcampinas, brazil\b"]),
        ("Mexico", [r"\bcinvestav\b"]),
        ("Greece", [r"\bforth\b", r"\bheraklion\b", r"\bcrete, greece\b"]),
        ("Canada", [r"\bnational capital commission\b"]),
        ("United Kingdom", [r"\buniversity of strathclyde\b", r"\bcity, university of london\b", r"\bbehavioural insights team\b"]),
        ("Netherlands", [r"\bnextcloud\b"]),
        ("Czech Republic", [r"\bczech technical university\b", r"\bprague\b"]),
        ("Italy", [r"\buniversity of bologna\b", r"\bdibris\b", r"\buniversity of genova\b"]),
        ("Cyprus", [r"\bcyprus university of technology\b"]),
        ("Estonia", [r"\btallinn\b"]),
        ("Sri Lanka", [r"\buniversity of colombo\b"]),
        ("Colombia", [r"\bbogot[áa]\b", r"\buniversidad de los andes\b"]),
        ("Pakistan", [r"\blums pakistan\b"]),
        ("Romania", [r"\btimisoara\b"]),
        ("Mongolia", [r"\bnew mongol institute of technology\b"]),
        ("Russia", [r"\bimmanuel kant baltic federal university\b"]),
        ("Ukraine", [r"\bnas of ukraine\b", r"\bkyiv, ukraine\b"]),
        ("Austria", [r"\bp[äa]dagogische hochschule augustinum\b", r"\bprivate p[äa]dagogische hochschule augustinum\b"]),
        ("Netherlands", [r"\bleiden university\b", r"\bamsterdam university of the arts\b"]),
        ("France", [r"\buniversit[ée] c[ôo]te d'?azur\b", r"\buniversite cote d'?azur\b", r"\buniversit[ée] bourgogne franche-comt[ée]\b", r"\b[ée]cole nationale de l'aviation civile\b", r"\benac\b", r"\bisae-supaero\b", r"\boffice national d'[ée]tudes et de recherches a[ée]rospatiales\b", r"\bonera\b", r"\blaboratoire d'analyse et d'architecture des syst[èe]mes\b", r"\blaas\b", r"\binstitut national des sciences appliqu[ée]es de toulouse\b", r"\binsa toulouse\b"]),
        ("Germany", [r"\buniversity of applied sciences emden leer\b", r"\bfreie universit[äa]t,? berlin\b", r"\bmpi-sws\b", r"\bmax planck institute for software systems\b"]),
        ("Greece", [r"\bnational and kapodistrian university of athens\b", r"\bindustrial systems institute\b", r"\bresearch center athena\b", r"\bpatras, greece\b"]),
        ("Pakistan", [r"\bdigital rights foundation\b", r"\blahore, pakistan\b"]),
        ("Portugal", [r"\buniversidade do porto\b", r"\buniversity of porto\b", r"\bfcup\b"]),
        ("Brazil", [r"\bfunda[çc][ãa]o getulio vargas\b", r"\brio de janeiro\b", r"\bufrgs\b", r"\buniversidade federal do rio grande do sul\b"]),
        ("Malaysia", [r"\buniversity of malaya\b", r"\bkuala lumpur\b"]),
        ("Colombia", [r"\buniversidad nacional de colombia\b", r"\bmedell[íi]n\b"]),
        ("Saudi Arabia", [r"\btaibah university\b", r"\bprince sattam bin abdulaziz university\b"]),
        ("China", [r"\bstate grid shanghai\b", r"\bshanghai municipal electric power\b", r"\bmatrixelements technologies\b", r"\bshanghai key laboratory of privacy-preserving computation\b"]),
        ("Belgium", [r"\bdistrinet\b", r"\bleuven, ku\b", r"\bku leuven\b"]),
        ("United Kingdom", [r"\bsecurity of advanced systems group, university of sheffield\b"]),
        ("United States", [r"\bdepartment of electrical and computer engineering, mississippi state university\b", r"\bmississippi state, ms\b"]),
        ("United States", [r"\bphiladelphia university\b", r"\bprovidence college\b"]),
        ("Italy", [r"\buniversity of rome tor vergata\b"]),
        ("South Korea", [r"\bchosun university\b"]),
        ("China", [r"\bshaanxi normal university\b"]),
        ("France", [r"\buniversite clermont auvergne\b", r"\buniversit[ée] clermont auvergne\b"]),
        ("Poland", [r"\bideas-ncbr\b"]),
        ("United States", [r"\binterdigital\b", r"\bf5, inc\.\b", r"\bf5\b", r"\bopenai\b", r"\bdropbox\b", r"\bfigma\b", r"\blyft\b", r"\bfireeye\b", r"\bswirlds\b", r"\bsquare inc\.\b"]),
        ("Japan", [r"\bnec corporation\b"]),
        ("United States", [r"\bcity university of new york\b"]),
        ("Poland", [r"\bwroclaw university of science and technology\b"]),
        ("Germany", [r"\bcriminological research institute of lower saxony\b"]),
        ("Slovakia", [r"\bbratislava, slovakia\b"]),
        ("France", [r"\banssi\b", r"\bens paris\b", r"\buniversit[ée] paris-diderot\b", r"\buniversite paris-diderot\b"]),
        ("Austria", [r"\btu graz\b"]),
        ("Germany", [r"\bbergische universit[äa]t wuppertal\b"]),
        ("Luxembourg", [r"\bdcs\b"]),
        ("Belgium", [r"\bfnrs\b", r"\bicteam\b"]),
        ("Singapore", [r"\btemasek polytechnic\b", r"\btemasek labs ntu\b"]),
        ("United States", [r"\bnaval postgraduate school\b", r"\bgtri\b", r"\bwashington and lee university\b", r"\brobinhood\b", r"\bwest virginia university\b", r"\buniversity of michgan\b"]),
        ("China", [r"\bcommercial cryptography testing center of state cryptography administration\b", r"\bsklcs, iscas\b"]),
        ("Sweden", [r"\blink[öo]ping university\b"]),
        ("Taiwan", [r"\bnational chiao-tung university\b"]),
        ("United Kingdom", [r"\buniversity of york\b", r"\barm limited\b"]),
        ("Germany", [r"\bhumboldt-universit[äa]t zu berlin\b"]),
        ("Austria", [r"\buniversit[äa]t wien\b"]),
        ("Portugal", [r"\buniversity of minho and inesc tec\b"]),
        ("Israel", [r"\bradware\b"]),
        ("United States", [r"\bsymantec research labs\b", r"\bzcash foundation\b"]),
    ]
)

US_PATTERN_RULES.extend(
    [
        r"\baccenture labs\b",
        r"\baccenture\b",
        r"\bcarnegie mellon\b",
        r"\bcmu\b",
        r"\bcmu, ic3\b",
        r"\buniversity of pittsburgh\b",
        r"\belectrical and computer engineering department, university of pittsburgh\b",
        r"\bnist\b",
        r"\bgaithersburg, maryland\b",
        r"\bfastly labs\b",
        r"\bj\.?\s*p\.?\s*morgan\b",
        r"\blawrence berkeley national laboratory\b",
        r"\bwellesley college\b",
        r"\bnetrise\b",
        r"\bu\.s\. army research laboratory\b",
        r"\bncsa\b",
        r"\blafayette college\b",
        r"\bauburn university\b",
        r"\bstate university of new york at buffalo\b",
        r"\buniversity at buffalo\b",
        r"\btor project\b",
        r"\bsignal messenger\b",
        r"\bkaleidoscope blockchain\b",
        r"\bcoconut research institute\b",
        r"\bnexus\b",
        r"\bpeckshield\b",
        r"\bzero point dynamics\b",
        r"\buniversity of st\. thomas\b",
        r"\bisothermal community college\b",
        r"\bjohns hopkins medicine\b",
        r"\bamerican jewish world service\b",
        r"\bjoint center for quantum information and computer science\b",
        r"\bpomona college\b",
        r"\bstevens insititute of technology\b",
        r"\bstevens institute of technology\b",
        r"\bf5, inc\.\b",
        r"\bf5 inc\b",
        r"\bcoinbase\b",
        r"\balgorand\b",
        r"\baxiom\b",
        r"\bfordefi\b",
        r"\bcle[o]? ai\b",
        r"\buniversity of central oklahoma\b",
        r"\bwhova\b",
        r"\blaboratory for advanced cybersecurity research\b",
        r"\bxailient\b",
    ]
)


def normalize_space(value: str) -> str:
    """规范化 HTML 实体、Unicode 变体与重复空白。"""
    value = html.unescape(value)
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("’", "'")
    return re.sub(r"\s+", " ", value).strip()


TRAILING_COUNTRY_PAREN_PATTERN = re.compile(
    r"\s*\(("
    r"United States|United Kingdom|China|Japan|Germany|France|Canada|Singapore|Australia|"
    r"Netherlands|Denmark|Switzerland|Israel|Spain|Italy|South Korea|India|Austria|Belgium|"
    r"Brazil|Qatar|Sweden|Norway|Finland|Ireland|Pakistan|Saudi Arabia|United Arab Emirates|"
    r"Greece|Czech Republic|New Zealand|Portugal|Romania|Thailand|Estonia|Mexico|Cyprus|"
    r"Sri Lanka|Colombia|Mongolia|Russia|Ukraine|Poland|Turkey|Hungary|Malaysia|Egypt|"
    r"Luxembourg|Taiwan|Hong Kong"
    r")\)$",
    re.IGNORECASE,
)


def clean_institution_label(value: str) -> str:
    """在匹配前去除机构名称尾部的国家后缀。"""
    text = normalize_space(value)
    if not text:
        return ""
    return normalize_space(TRAILING_COUNTRY_PAREN_PATTERN.sub("", text))


PROTECTED_COMPOSITE_INSTITUTION_PATTERN = re.compile(
    r"\b("
    r"Science and Technology|"
    r"Posts and Telecommunications|"
    r"Economics and Technology|"
    r"Research and Technology|"
    r"Information and Communications Technology|"
    r"Polytechnic Institute and State University|"
    r"Academy of Mathematics and System Science|"
    r"Academy of Mathematics and Systems Science|"
    r"Beijing Institute of Mathematical Sciences and Application|"
    r"Beijing Institute of Mathematical Sciences and Applications|"
    r"Computer Science and Artificial Intelligence|"
    r"Computer Science and Engineering|"
    r"Computer Science and Information Technology|"
    r"Computer and Cyber Security|"
    r"School of Electrical Engineering and Computer Science|"
    r"Mathematics and Computer Science|"
    r"Applied Mathematics and Computer Science|"
    r"Electrical and Computer Engineering|"
    r"Information and Engineering|"
    r"Information Engineering, CAS|"
    r"Trustworthy Distributed Computing and Service|"
    r"High Performance Computing and Networking|"
    r"Security and Privacy|"
    r"Technology and Economics|"
    r"Agriculture and Technology|"
    r"Computer Science and Control|"
    r"Network Sciences and Cyberspace|"
    r"Physical and Mathematical Sciences|"
    r"National and Kapodistrian University|"
    r"Budapest University of Technology and Economics|"
    r"Institute of Science and Technology Austria|"
    r"King Abdulaziz City for Science and Technology|"
    r"Applied Sciences and Arts|"
    r"Electronics and Telecommunications Research Institute|"
    r"Electronics and Applied Mathematics|"
    r"Advanced Computing and Intelligence Engineering|"
    r"London School of Economics and Political Science|"
    r"William & Mary|"
    r"Centrum Wiskunde & Informatica"
    r")\b",
    re.IGNORECASE,
)

SPLIT_NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"^\s*School of Electrical Engineering\s*;\s*Computer Science,\s*Oregon State University,\s*Corvallis,\s*OR,\s*USA\s*$",
            re.IGNORECASE,
        ),
        "School of Electrical Engineering and Computer Science, Oregon State University, Corvallis, OR, USA",
    ),
    (
        re.compile(
            r"^\s*ICTEAM\s*/\s*ELEN\s*/\s*Crypto Group,\s*UCL,\s*Louvain-la-Neuve,\s*Belgium\s*$",
            re.IGNORECASE,
        ),
        "Crypto Group, ICTEAM Institute, UCLouvain, Louvain-la-Neuve, Belgium",
    ),
    (
        re.compile(
            r"^\s*National Research Council\s*;\s*Institute for High Performance Computing and Networking\s*$",
            re.IGNORECASE,
        ),
        "National Research Council, Institute for High Performance Computing and Networking",
    ),
    (
        re.compile(r"^\s*Brown,\s*UVa\s*$", re.IGNORECASE),
        "Brown University; University of Virginia",
    ),
    (
        re.compile(r"^\s*TAU,\s*Stellar Foundation\s*$", re.IGNORECASE),
        "TAU; Stellar Foundation",
    ),
    (
        re.compile(r"^\s*Technion,\s*Amazon(?:/AWS)?\s*$", re.IGNORECASE),
        "Technion; Amazon Web Services",
    ),
    (
        re.compile(
            r"^\s*College of Computer Science\s*;\s*Engineering,\s*Taibah University,\s*Medina,\s*Saudi Arabia\s*$",
            re.IGNORECASE,
        ),
        "College of Computer Science and Engineering, Taibah University, Medina, Saudi Arabia",
    ),
    (
        re.compile(
            r"^\s*Department of Applied Mathematics\s*;\s*Computer Science,\s*Technical University of Denmark\s*$",
            re.IGNORECASE,
        ),
        "Department of Applied Mathematics and Computer Science, Technical University of Denmark",
    ),
    (
        re.compile(
            r"^\s*School of Computing\s*;\s*Information Technology,\s*University of Wollongong\s*$",
            re.IGNORECASE,
        ),
        "School of Computing and Information Technology, University of Wollongong",
    ),
    (
        re.compile(
            r"^\s*Paul G\. Allen School of Computer Science\s*;\s*Engineering,\s*University of Washington\s*$",
            re.IGNORECASE,
        ),
        "Paul G. Allen School of Computer Science and Engineering, University of Washington",
    ),
    (
        re.compile(
            r"^\s*Institute of Information\s*;\s*Engineering,\s*CAS\s*$",
            re.IGNORECASE,
        ),
        "Institute of Information Engineering, CAS",
    ),
    (
        re.compile(
            r"^\s*Key Laboratory of Trustworthy Distributed Computing\s*;\s*Service\s*\(BUPT\),\s*Ministry of Education\s*$",
            re.IGNORECASE,
        ),
        "Key Laboratory of Trustworthy Distributed Computing and Service (BUPT), Ministry of Education",
    ),
    (
        re.compile(
            r"^\s*BULL SAS,\s*Universit[ée]\s+Grenoble Alpes\s*$",
            re.IGNORECASE,
        ),
        "BULL SAS; Université Grenoble Alpes",
    ),
    (
        re.compile(
            r"\bImperial College London,\s*UCL Centre for Blockchain Technologies\b",
            re.IGNORECASE,
        ),
        "Imperial College London; UCL Centre for Blockchain Technologies",
    ),
    (
        re.compile(
            r"\bInstitute for Network Science and Cyberspace\s*&\s*BNRist,\s*Tsinghua University\b",
            re.IGNORECASE,
        ),
        "Institute for Network Science and Cyberspace, Tsinghua University; BNRist, Tsinghua University",
    ),
    (
        re.compile(
            r"\b((?:Department|School) of Computer Science)\s*;\s*Engineering\b",
            re.IGNORECASE,
        ),
        r"\1 and Engineering",
    ),
    (
        re.compile(
            r"\bInstitute of Information\s*;\s*Communication Technologies,\s*Electronics\s*;\s*Applied Mathematics\b",
            re.IGNORECASE,
        ),
        "Institute of Information, Communication Technologies, Electronics and Applied Mathematics",
    ),
    (
        re.compile(
            r"\bDept\.\s+of Computer Science\s*;\s*Engineering\b",
            re.IGNORECASE,
        ),
        "Dept. of Computer Science and Engineering",
    ),
    (
        re.compile(
            r"\bDepartment of Computer Science\s*;\s*Engineering\b",
            re.IGNORECASE,
        ),
        "Department of Computer Science and Engineering",
    ),
    (
        re.compile(
            r"\bElectrical\s*;\s*Computer Engineering\b",
            re.IGNORECASE,
        ),
        "Electrical and Computer Engineering",
    ),
    (
        re.compile(
            r"\bLaboratory for Advanced Computing\s*;\s*Intelligence Engineering\b",
            re.IGNORECASE,
        ),
        "Laboratory for Advanced Computing and Intelligence Engineering",
    ),
    (
        re.compile(
            r"\bImperial College London\s*&amp\s*;?",
            re.IGNORECASE,
        ),
        "Imperial College London &",
    ),
    (
        re.compile(
            r"\b(ETH Zurich|Georgia Institute of Technology|Paderborn University|Purdue University|Tokyo Institute of Technology)\s*&amp\s*$",
            re.IGNORECASE,
        ),
        r"\1",
    ),
]

PROTECTED_TOKEN_TEMPLATE = "__INST_PROTECTED_{index}__"
DROP_IF_SUBSTRING_FRAGMENT_LABELS = {
    "Software",
}


def _normalize_split_text(value: str) -> str:
    """对含噪的多机构字符串执行拆分前清洗。"""
    text = value
    for pattern, replacement in SPLIT_NORMALIZATION_RULES:
        text = pattern.sub(replacement, text)
    return text


def _protect_composite_phrases(value: str) -> tuple[str, dict[str, str]]:
    """保护包含分隔符但不应被拆开的短语。"""
    replacements: dict[str, str] = {}

    def replacer(match: re.Match[str]) -> str:
        token = PROTECTED_TOKEN_TEMPLATE.format(index=len(replacements))
        protected = re.sub(r"\s*&\s*", " __AMP__ ", match.group(0))
        protected = re.sub(r"\s+and\s+", " __AND__ ", protected, flags=re.IGNORECASE)
        replacements[token] = protected
        return token

    return PROTECTED_COMPOSITE_INSTITUTION_PATTERN.sub(replacer, value), replacements


def _restore_composite_phrases(value: str, replacements: dict[str, str]) -> str:
    """在拆分结束后恢复被保护的短语。"""
    restored = value
    for token, protected in replacements.items():
        restored = restored.replace(token, protected)
    restored = restored.replace("__AMP__", "&").replace("__AND__", "and")
    return normalize_space(restored)


def split_reference_institution_parts(value: str, known_names: set[str] | None = None) -> list[str]:
    """将原始机构字符串拆分为机构级参考片段。"""
    normalized = clean_institution_label(value)
    if not normalized:
        return []
    normalized = _normalize_split_text(normalized)
    protected_text, replacements = _protect_composite_phrases(normalized)

    parts: list[str] = [protected_text]
    split_mode = "none"
    if ";" in protected_text:
        parts = [part.strip() for part in protected_text.split(";") if part.strip()]
        split_mode = "semicolon"
    elif ", and " in protected_text:
        parts = [part.strip(" ,") for part in re.split(r",\s+and\s+", protected_text) if part.strip(" ,")]
        split_mode = "comma_and"
    elif " & " in protected_text:
        parts = [part.strip() for part in protected_text.split(" & ") if part.strip()]
        split_mode = "ampersand"
    elif " and " in protected_text:
        parts = [part.strip() for part in re.split(r"\s+and\s+", protected_text) if part.strip()]
        split_mode = "and"
    elif "/" in protected_text:
        parts = [part.strip() for part in protected_text.split("/") if part.strip()]
        split_mode = "slash"

    cleaned = [
        clean_institution_label(_restore_composite_phrases(part, replacements))
        for part in parts
        if normalize_space(part)
    ]
    if len(cleaned) > 1:
        cleaned = [
            part
            for part in cleaned
            if not (
                part in DROP_IF_SUBSTRING_FRAGMENT_LABELS
                and any(part.casefold() in other.casefold() and len(other) > len(part) for other in cleaned if other != part)
            )
        ]
    if len(cleaned) <= 1:
        return [normalized]
    if split_mode == "comma_known" and known_names is not None and not all(part.casefold() in known_names for part in cleaned):
        return [normalized]
    return cleaned


def csv_row_get(row: dict[str, str], *keys: str) -> str:
    """在多个候选列名中返回第一个非空 CSV 值。"""
    normalized = {
        normalize_space(key).lstrip("\ufeff").strip('"'): value
        for key, value in row.items()
    }
    for key in keys:
        if key in normalized:
            return normalized[key]
    return ""


def load_override_rows(path: Path, classification_factory: Callable[[str, str, float, str], Any]) -> dict[str, Any]:
    """加载按规范化机构文本维护的手工覆盖规则。"""
    overrides = load_reference_registry_overrides(classification_factory)
    if not path.exists():
        return overrides
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            inst = normalize_space(csv_row_get(row, "inst"))
            if not inst:
                continue
            country = normalize_space(csv_row_get(row, "country"))
            if not country:
                detected_country, _detected_reason = detect_country_from_patterns(inst.casefold())
                country = detected_country or "Unknown"
            reason = normalize_space(csv_row_get(row, "reason")) or "override"
            overrides[inst.casefold()] = classification_factory(country, "override", 1.0, reason)
    return overrides


def load_reference_registry_overrides(
    classification_factory: Callable[[str, str, float, str], Any]
) -> dict[str, Any]:
    """从机构参考表中加载机构库驱动的国家映射。"""
    root = Path(__file__).resolve().parents[2]
    alias_path = root / "conference-dataset-normalization" / "references" / "institution_aliases.csv"
    registry_path = root / "conference-dataset-normalization" / "references" / "institution_registry.csv"
    if not alias_path.exists() or not registry_path.exists():
        return {}

    registry_country_by_id: dict[str, str] = {}
    canonical_name_by_id: dict[str, str] = {}
    registry_type_by_id: dict[str, str] = {}
    reference_names: set[str] = set()
    with registry_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            institution_id = normalize_space(csv_row_get(row, "institution_id"))
            if not institution_id:
                continue
            canonical_name = normalize_space(csv_row_get(row, "canonical_name"))
            canonical_name_by_id[institution_id] = canonical_name
            registry_country_by_id[institution_id] = normalize_space(csv_row_get(row, "country"))
            registry_type_by_id[institution_id] = normalize_space(csv_row_get(row, "type"))
            if canonical_name:
                reference_names.add(canonical_name.casefold())

    alias_rows: list[tuple[str, str]] = []
    with alias_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            alias = normalize_space(csv_row_get(row, "alias"))
            institution_id = normalize_space(csv_row_get(row, "institution_id"))
            if alias and institution_id:
                alias_rows.append((alias, institution_id))
                reference_names.add(alias.casefold())

    overrides: dict[str, Any] = {}
    for alias, institution_id in alias_rows:
        country = registry_country_by_id.get(institution_id, "")
        institution_type = registry_type_by_id.get(institution_id, "")
        effective_country = country or ("None" if institution_type == "independent" else "")
        if alias and effective_country and len(split_reference_institution_parts(alias)) == 1:
            overrides[alias.casefold()] = classification_factory(
                effective_country,
                "reference_registry",
                0.98,
                "reference_registry_exact",
            )

    for institution_id, canonical_name in canonical_name_by_id.items():
        country = registry_country_by_id.get(institution_id, "")
        institution_type = registry_type_by_id.get(institution_id, "")
        effective_country = country or ("None" if institution_type == "independent" else "")
        if canonical_name and effective_country and len(split_reference_institution_parts(canonical_name)) == 1:
            overrides[canonical_name.casefold()] = classification_factory(
                effective_country,
                "reference_registry",
                0.98,
                "reference_registry_exact",
            )
    return overrides


def detect_country_from_patterns(lower: str) -> tuple[str | None, str | None]:
    """用整理好的国家正则规则匹配规范化机构字符串。"""
    for country, patterns in COUNTRY_PATTERN_RULES:
        for pattern in patterns:
            if re.search(pattern, lower):
                return country, f"country_keyword_{country.casefold().replace(' ', '_')}"
    return None, None


def classify_with_patterns(
    affiliation: str,
    *,
    overrides: dict[str, Any] | None,
    exact_aliases: set[str],
    non_us_patterns: list[str],
    us_patterns: list[str],
    classification_factory: Callable[[str, str, float, str], Any],
) -> Any:
    """优先使用覆盖规则、其次使用正则启发式对机构字符串分类。"""
    normalized = normalize_space(affiliation)
    lower = normalized.casefold()
    if overrides and lower in overrides:
        return overrides[lower]
    if any(
        marker in lower
        for marker in [
            "hubei minzu university",
            "academy of mathematics and system science, chinese academy sciences",
            "academy of mathematics and systems science, chinese academy of sciences",
            "beijing institute of mathematical sciences and application",
            "beijing institute of mathematical sciences and applications",
            "yale-nus college",
            "chinese university of hong kong, shenzhen",
            "the chinese university of hong kong, shenzhen",
            "university of chinese academy of sciences",
        ]
):
        if "yale-nus college" in lower:
            return classification_factory("Singapore", "rule", 0.95, "reference_alias_singapore")
        return classification_factory("China", "rule", 0.95, "reference_alias_china")
    if lower in exact_aliases:
        return classification_factory("United States", "rule", 1.0, "exact_us_alias")
    if any(
        marker in lower
        for marker in [
            "aws",
            "amazon web services",
            "university of southern california",
        ]
    ):
        return classification_factory("United States", "rule", 0.95, "reference_alias_us")
    if lower == "stanford":
        return classification_factory("United States", "rule", 0.95, "reference_alias_us")
    country, country_reason = detect_country_from_patterns(lower)
    if country is not None and country != "United States":
        return classification_factory(country, "rule", 0.95, country_reason or "country_keyword")
    for pattern in US_PATTERN_RULES:
        if re.search(pattern, lower):
            return classification_factory("United States", "rule", 0.95, "us_keyword")
    for pattern in us_patterns:
        if re.search(pattern, lower):
            return classification_factory("United States", "rule", 0.95, "us_keyword")
    if re.search(r"\b(united states|usa|u\.s\.a\.|, us|, usa)\b", lower):
        return classification_factory("United States", "rule", 0.95, "us_location_marker")
    if country is not None:
        return classification_factory(country, "rule", 0.95, country_reason or "country_keyword")
    for pattern in non_us_patterns:
        if re.search(pattern, lower):
            return classification_factory("Unknown", "rule", 0.7, "non_us_keyword")
    return classification_factory("Unknown", "unresolved", 0.0, "needs_review")
