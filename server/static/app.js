// purpose: 拖拽/选择 → 上传转换 → 展示结果与下载 的前端逻辑
const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const list = document.getElementById('list');
const footer = document.getElementById('footer');
const zipBtn = document.getElementById('zip');
const clearBtn = document.getElementById('clear');
let lastZipUrl = null;

// 展示支持的格式
fetch('/api/formats').then(r => r.json()).then(d => {
  document.getElementById('formats').textContent = '支持:' + d.formats.join(' · ');
}).catch(() => {});

// 拖拽高亮
['dragenter', 'dragover'].forEach(ev =>
  drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach(ev =>
  drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('over'); }));

drop.addEventListener('drop', e => handleFiles(e.dataTransfer.files));
drop.addEventListener('click', () => fileInput.click());
document.getElementById('pick').addEventListener('click', e => { e.stopPropagation(); fileInput.click(); });
fileInput.addEventListener('change', () => handleFiles(fileInput.files));
clearBtn.addEventListener('click', () => { list.innerHTML = ''; footer.classList.add('hidden'); zipBtn.classList.add('hidden'); });
zipBtn.addEventListener('click', () => { if (lastZipUrl) window.location = lastZipUrl; });

function fmtSize(b) {
  if (b < 1024) return b + ' B';
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
  return (b / 1048576).toFixed(2) + ' MB';
}

function rowLoading(name) {
  const li = document.createElement('li');
  li.className = 'item';
  li.innerHTML = `<div class="spin"></div><div class="meta"><div class="nm"></div>
    <div class="st">转换中…</div></div>`;
  li.querySelector('.nm').textContent = name;
  list.appendChild(li);
  return li;
}

function fillResult(li, r) {
  li.className = 'item ' + (r.ok ? 'ok' : 'err');
  if (r.ok) {
    li.innerHTML = `<div class="ic">✅</div><div class="meta">
      <div class="nm"></div><div class="st">已转 PDF · ${fmtSize(r.size)}</div></div>
      <a class="btn dl" href="${r.url}">⬇ 下载</a>`;
  } else {
    li.innerHTML = `<div class="ic">⚠️</div><div class="meta">
      <div class="nm"></div><div class="st err"></div></div>`;
    li.querySelector('.st').textContent = r.error;
  }
  li.querySelector('.nm').textContent = r.name;
}

async function handleFiles(fileList) {
  const files = Array.from(fileList);
  if (!files.length) return;
  footer.classList.remove('hidden');
  const rows = files.map(f => rowLoading(f.name));

  const fd = new FormData();
  files.forEach(f => fd.append('files', f, f.name));

  try {
    const res = await fetch('/api/convert', { method: 'POST', body: fd });
    const data = await res.json();
    // 按返回顺序回填(后端按上传顺序处理)
    data.results.forEach((r, i) => fillResult(rows[i], r));
    if (data.zip_url) { lastZipUrl = data.zip_url; zipBtn.classList.remove('hidden'); }
  } catch (err) {
    rows.forEach(li => fillResult(li, { ok: false, name: '', error: '请求失败:' + err }));
  }
  fileInput.value = '';
}
