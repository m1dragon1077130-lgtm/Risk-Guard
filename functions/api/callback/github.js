export async function onRequest(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const error = url.searchParams.get('error');
  
  if (error) return redirect('/login.html?error=cancelled');
  if (!code) return redirect('/login.html?error=invalid');
  
  const tokenRes = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST',
    headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: env.GITHUB_CLIENT_ID,
      client_secret: env.GITHUB_CLIENT_SECRET,
      code: code,
    }),
  });
  
  const tokenData = await tokenRes.json();
  if (!tokenData.access_token) return redirect('/login.html?error=token_failed');
  
  const userRes = await fetch('https://api.github.com/user', {
    headers: { 'Authorization': `token ${tokenData.access_token}`, 'User-Agent': 'RiskGuard' },
  });
  const user = await userRes.json();
  
  // ذخیره در Supabase
  if (env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
    try {
      await fetch(`${env.SUPABASE_URL}/rest/v1/users`, {
        method: 'POST',
        headers: {
          'apikey': env.SUPABASE_SERVICE_KEY,
          'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          'Content-Type': 'application/json',
          'Prefer': 'resolution=merge-duplicates',
        },
        body: JSON.stringify({
          github_id: user.id,
          github_username: user.login,
          github_name: user.name || '',
          github_avatar: user.avatar_url || '',
          github_token: tokenData.access_token,
        }),
      });
    } catch (e) {
      console.error('DB error:', e);
    }
  }
  
  // Session شامل توکن GitHub
  const sessionData = btoa(JSON.stringify({
    github_id: user.id,
    username: user.login,
    name: user.name,
    avatar: user.avatar_url,
    gh_token: tokenData.access_token,
  }));
  
  return new Response(null, {
    status: 302,
    headers: {
      'Location': '/dashboard.html',
      'Set-Cookie': `session=${sessionData}; HttpOnly; Secure; SameSite=Lax; Max-Age=86400; Path=/`,
    },
  });
}

function redirect(location) {
  return new Response(null, { status: 302, headers: { 'Location': location } });
}
