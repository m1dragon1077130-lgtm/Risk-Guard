export async function onRequest(context) {
  const { env, request } = context;
  
  const cookies = request.headers.get('Cookie') || '';
  const sessionMatch = cookies.match(/session=([^;]+)/);
  
  if (!sessionMatch) return json({ error: 'Not logged in' }, 401);
  
  let sessionData;
  try {
    sessionData = JSON.parse(atob(sessionMatch[1]));
  } catch {
    return json({ error: 'Invalid session' }, 401);
  }
  
  if (!sessionData.gh_token) return json({ error: 'GitHub token missing' }, 401);
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  
  const ghToken = sessionData.gh_token;
  const username = sessionData.username;
  const repo = `${username}/riskguard`;
  
  try {
    // چک کن مخزن riskguard وجود داره؟
    const checkRes = await ghFetch(
      `https://api.github.com/repos/${repo}`,
      ghToken
    );
    
    if (checkRes.status === 200) {
      return json({
        ok: true,
        message: 'مخزن از قبل وجود دارد',
        already_exists: true,
        repo: `https://github.com/${repo}`,
      });
    }
    
    // Fork کن
    const forkRes = await ghFetch(
      `https://api.github.com/repos/m1dragon1077130-lgtm/riskguard-template/forks`,
      ghToken,
      'POST'
    );
    
    if (!forkRes.ok && forkRes.status !== 202) {
      return json({ 
        error: 'Fork failed: ' + await forkRes.text() 
      }, 500);
    }
    
    // فقط ۲ ثانیه صبر کن (فقط برای شروع Fork)
    await new Promise(r => setTimeout(r, 2000));
    
    return json({
      ok: true,
      message: 'Fork در حال انجام است. ۳۰-۶۰ ثانیه صبر کن، بعد دکمه‌ی اتصال ربات رو بزن.',
      pending: true,
      repo: `https://github.com/${repo}`,
    });
    
  } catch (err) {
    console.error('Fork error:', err);
    return json({ error: err.message }, 500);
  }
}

function ghFetch(url, token, method = 'GET', body = null) {
  const options = {
    method,
    headers: {
      'Authorization': `token ${token}`,
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'RiskGuard',
    },
  };
  if (body) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  return fetch(url, options);
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
