import {Localized} from '../../../../i18n/locale';

// Short teaser; the full explanation and usage guide live on the About SV page.
export default function MultiFactorIntro(){
 return <Localized><section className="mfIntro" aria-labelledby="mfIntroTitle">
  <small>关于 Sage Vista</small>
  <h2 id="mfIntroTitle">三重滤网式的顺势回调系统</h2>
  <p>SV 先用月线和周线确认长期趋势，再在日线上寻找回调后的入场形态，最后用多周期共振评分排序。建议按“大盘 → 行业 → 个股”的顺序使用。</p>
  <a href="/zh/watch/resonance/about#how-to-use">📘 如何使用 SV →</a>
 </section></Localized>;
}
