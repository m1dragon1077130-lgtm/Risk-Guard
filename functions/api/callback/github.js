export async function onRequest(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');
  
  if (error) {
    return redirect('/login.html?error=cancelled');
  }
  
  if (!code || !state) {
    return redirect('/login.html?error=invalid');
  }
  
  if (!env.GITHUB_CLIENT_ID || !env.GITHUB_CLIENT_SECRET) {
    return new Response('Server error: env vars not set', { status: 500 });
  }
  
  try {
    const tokenRes = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        client_id: env.GITHUB_CLIENT_ID,
        client_secret: env.GITHUB_CLIENT_SECRET,
        code: code,
      }),
    });
    
    const tokenData = await tokenRes.json();
    
    if (!tokenData.access_token) {
      return redirect('/login.html?error=token_failed');
    }
    
    const userRes = await fetch('https://api.github.com/user', {
      headers: {
        'Authorization': `token ${tokenData.access_token}`,
        'User-Agent': 'RiskGuard',
      },
    });
    
    const user = await userRes.json();
    
    // ذخیره در Supabase
    if (env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
      try {
        const sbRes = await fetch(`${env.SUPABASE_URL}/rest/v1/users?on_conflict=github_id`, {
          method: 'POST',
          headers: {
            'apikey': env.SUPABASE_SERVICE_KEY,
            'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
            'Content-Type': 'application/json',
            'Prefer': 'resolution=merge-duplicates,return=minimal',
          },
          body: JSON.stringify({
            github_id: user.id,
            github_username: user.login,
            github_name: user.name || '',
            github_avatar: user.avatar_url || '',
            github_token: tokenData.access_token,
          }),
        });
        
        if (!sbRes.ok) {
          const errText = await sbRes.text();
          console.error('Supabase error:', errText);
        }
      } catch (dbErr) {
        console.error('DB exception:', dbErr);
      }
    }
    
    const sessionData = btoa(JSON.stringify({
      github_id: user.id,
      username: user.login,
      name: user.name,
      avatar: user.avatar_url,
    }));
    
    return new Response(null, {
      status: 302,
      headers: {
        'Location': '/dashboard.html',
        'Set-Cookie': `session=${sessionData}; HttpOnly; Secure; SameSite=Lax; Max-Age=86400; Path=/`,
      },
    });
    
  } catch (err) {
    return new Response(`Error: ${err.message}`, { status: 500 });
  }
}

function redirect(location) {
  return new Response(null, {
    status: 302,
    headers: { 'Location': location },
  });
}
