import nacl from '../_lib/nacl.js';

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
  
  if (!sessionData.gh_token) {
    return json({ error: 'GitHub token missing' }, 401);
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
  
  const { api_key, api_secret } = body;
  
  if (!api_key || !api_secret) {
    return json({ error: 'API Key و Secret الزامی هستن' }, 400);
  }
  
  const ghToken = sessionData.gh_token;
  const username = sessionData.username;
  const repo = `${username}/riskguard`;
  
  try {
    let checkRes = await ghFetch(`https://api.github.com/repos/${repo}`, ghToken);
    
    if (checkRes.status === 404) {
      const forkRes = await ghFetch(
        `https://api.github.com/repos/m1dragon1077130-lgtm/riskguard-template/forks`,
        ghToken,
        'POST'
      );
      
      if (!forkRes.ok && forkRes.status !== 202) {
        return json({ error: 'Fork failed: ' + await forkRes.text() }, 500);
      }
      
      let attempts = 0;
      while (attempts < 15) {
        await new Promise(r => setTimeout(r, 2000));
        attempts++;
        checkRes = await ghFetch(`https://api.github.com/repos/${repo}`, ghToken);
        if (checkRes.status === 200) break;
      }
      
      if (checkRes.status !== 200) {
        return json({ error: 'Fork timeout' }, 500);
      }
    }
    
    await new Promise(r => setTimeout(r, 5000));
    
    const pkRes = await ghFetch(
      `https://api.github.com/repos/${repo}/actions/secrets/public-key`,
      ghToken
    );
    
    if (!pkRes.ok) {
      return json({ error: 'Cannot get public key: ' + await pkRes.text() }, 500);
    }
    
    const pk = await pkRes.json();
    
    const secretsToSet = { TT_API_KEY: api_key, TT_API_SECRET: api_secret };
    
    for (const [name, value] of Object.entries(secretsToSet)) {
      const encrypted = encryptSecret(value, pk.key);
      
      const secretRes = await ghFetch(
        `https://api.github.com/repos/${repo}/actions/secrets/${name}`,
        ghToken,
        'PUT',
        { encrypted_value: encrypted, key_id: pk.key_id }
      );
      
      if (!secretRes.ok) {
        return json({ error: `Secret ${name} failed: ${await secretRes.text()}` }, 500);
      }
    }
    
    await ghFetch(
      `https://api.github.com/repos/${repo}/actions/permissions`,
      ghToken,
      'PUT',
      { enabled: true, allowed_actions: 'all' }
    );
    
    await new Promise(r => setTimeout(r, 3000));
    
    await ghFetch(
      `https://api.github.com/repos/${repo}/actions/workflows/riskguard.yml/dispatches`,
      ghToken,
      'POST',
      { ref: 'main' }
    );
    
    if (env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
      await fetch(
        `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}`,
        {
          method: 'PATCH',
          headers: {
            'apikey': env.SUPABASE_SERVICE_KEY,
            'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ is_active: true, updated_at: new Date().toISOString() }),
        }
      );
    }
    
    return json({ ok: true, message: 'ربات فعال شد!', repo: `https://github.com/${repo}` });
    
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
      'User-Agent': 'RiskGuard',
    },
  };
  if (body) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  return fetch(url, options);
}

function encryptSecret(secretValue, publicKeyBase64) {
  const publicKey = base64ToUint8(publicKeyBase64);
  const message = new TextEncoder().encode(secretValue);
  const ephemeralKeyPair = nacl.box.keyPair();
  const nonce = nacl.randomBytes(24);
  const encrypted = nacl.box(message, nonce, publicKey, ephemeralKeyPair.secretKey);
  const sealedBox = new Uint8Array(ephemeralKeyPair.publicKey.length + encrypted.length);
  sealedBox.set(ephemeralKeyPair.publicKey, 0);
  sealedBox.set(encrypted, ephemeralKeyPair.publicKey.length);
  return uint8ToBase64(sealedBox);
}

function base64ToUint8(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function uint8ToBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
                 }
