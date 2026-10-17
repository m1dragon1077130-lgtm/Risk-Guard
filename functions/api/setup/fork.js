export async function onRequest(context) {
  const { env, request } = context;
  const cookies = request.headers.get('Cookie') || '';
  const sessionMatch = cookies.match(/session=([^;]+)/);
  if (!sessionMatch) return json({ error: 'Not logged in' }, 401);
  
  let sessionData;
  try { sessionData = JSON.parse(atob(sessionMatch[1])); } catch { return json({ error: 'Invalid session' }, 401); }
  
  const ghToken = sessionData.gh_token;
  const username = sessionData.username;
  const repo = `${username}/riskguard`;
  
  try {
    // چک کن اگه از قبل ساخته شده
    let checkRes = await ghFetch(`https://api.github.com/repos/${repo}`, ghToken);
    if (checkRes.status === 200) {
      return json({ ok: true, status: 'ready' });
    }
    
    // درخواست Fork رو میفرستیم و اسمش رو riskguard میذاریم
    const forkRes = await ghFetch(`https://api.github.com/repos/m1dragon1077130-lgtm/riskguard-template/forks`, ghToken, 'POST', {
      name: "riskguard" // 👈 این خط خیلی مهمه
    });
    
    if (!forkRes.ok && forkRes.status !== 202) {
        return json({ error: 'Fork failed: ' + await forkRes.text() }, 500);
    }
    
    // فوراً برمیگردیم. سایت میفهمه که باید به کاربر بگه ۱ دقیقه صبر کنه
    return json({ ok: true, status: 'pending' });
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}

function ghFetch(url, token, method = 'GET', body = null) {
  const options = { 
    method, 
    headers: { 
      'Authorization': `token ${token}`, 
      'Accept': 'application/vnd.github.v3+json', 
      'User-Agent': 'RiskGuard' 
    } 
  };
  if (body) { 
    options.headers['Content-Type'] = 'application/json'; 
    options.body = JSON.stringify(body); 
  }
  return fetch(url, options);
}
function json(data, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
