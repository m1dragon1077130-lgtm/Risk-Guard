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
  
  if (request.method !== 'POST') {
    return json({ error: 'Method not allowed' }, 405);
  }
  
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'Invalid JSON' }, 400);
  }
  
  const config = {
    max_loss_usd: parseFloat(body.max_loss_usd) || 1,
    reward_ratio: parseFloat(body.reward_ratio) || 5,
    trigger_ratio: parseFloat(body.trigger_ratio) || 2,
    lock_profit_ratio: parseFloat(body.lock_profit_ratio) || 1,
    max_positions: parseInt(body.max_positions) || 1,
  };
  
  // اعتبارسنجی
  if (config.max_loss_usd < 0.5 || config.max_loss_usd > 10) {
    return json({ error: 'حداکثر ضرر باید بین 0.5 و 10 باشه' }, 400);
  }
  if (config.reward_ratio < 1 || config.reward_ratio > 20) {
    return json({ error: 'نسبت ریوارد باید بین 1 و 20 باشه' }, 400);
  }
  if (config.trigger_ratio >= config.reward_ratio) {
    return json({ error: 'آستانه قفل سود باید کمتر از ریوارد باشه' }, 400);
  }
  if (config.lock_profit_ratio >= config.trigger_ratio) {
    return json({ error: 'قفل سود باید کمتر از آستانه باشه' }, 400);
  }
  if (config.max_positions < 1 || config.max_positions > 5) {
    return json({ error: 'حداکثر معاملات باید بین 1 و 5 باشه' }, 400);
  }
  
  try {
    // ۱. ذخیره در Supabase
    const sbRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}`,
      {
        method: 'PATCH',
        headers: {
          'apikey': env.SUPABASE_SERVICE_KEY,
          'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          'Content-Type': 'application/json',
          'Prefer': 'return=minimal',
        },
        body: JSON.stringify({
          config: config,
          updated_at: new Date().toISOString(),
        }),
      }
    );
    
    if (!sbRes.ok) {
      const errText = await sbRes.text();
      return json({ error: 'DB error: ' + errText }, 500);
    }
    
    // ۲. آپدیت config.json توی مخزن کاربر
    const ghToken = sessionData.gh_token;
    const username = sessionData.username;
    const repo = `${username}/riskguard`;
    
    if (ghToken && username) {
      // SHA فایل فعلی
      const configFileRes = await fetch(
        `https://api.github.com/repos/${repo}/contents/config.json`,
        {
          headers: {
            'Authorization': `token ${ghToken}`,
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'RiskGuard',
          },
        }
      );
      
      if (configFileRes.ok) {
        const configData = await configFileRes.json();
        const sha = configData.sha;
        
        // محتوای جدید (با حفظ API Key)
        let existingConfig = {};
        try {
          const decoded = decodeURIComponent(escape(atob(configData.content)));
          existingConfig = JSON.parse(decoded);
        } catch {}
        
        const newConfig = {
          ...existingConfig,
          max_loss_usd: config.max_loss_usd,
          reward_ratio: config.reward_ratio,
          trigger_ratio: config.trigger_ratio,
          lock_profit_ratio: config.lock_profit_ratio,
          max_positions: config.max_positions,
        };
        
        const configStr = JSON.stringify(newConfig, null, 2);
        const contentB64 = btoa(unescape(encodeURIComponent(configStr)));
        
        // آپدیت فایل
        const updateRes = await fetch(
          `https://api.github.com/repos/${repo}/contents/config.json`,
          {
            method: 'PUT',
            headers: {
              'Authorization': `token ${ghToken}`,
              'Accept': 'application/vnd.github.v3+json',
              'User-Agent': 'RiskGuard',
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              message: 'Update config',
              content: contentB64,
              sha: sha,
            }),
          }
        );
        
        if (!updateRes.ok) {
          console.error('GitHub config update failed:', await updateRes.text());
        }
      }
    }
    
    return json({ ok: true, config });
    
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
