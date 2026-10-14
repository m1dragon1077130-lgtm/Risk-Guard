export async function onRequest(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');
  
  if (error) {
    return new Response(null, {
      status: 302,
      headers: { 'Location': '/login.html?error=cancelled' },
    });
  }
  
  if (!code || !state) {
    return new Response(null, {
      status: 302,
      headers: { 'Location': '/login.html?error=invalid' },
    });
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
      return new Response(null, {
        status: 302,
        headers: { 'Location': '/login.html?error=token_failed' },
      });
    }
    
    const userRes = await fetch('https://api.github.com/user', {
      headers: {
        'Authorization': `token ${tokenData.access_token}`,
        'User-Agent': 'RiskGuard',
      },
    });
    
    const user = await userRes.json();
    
    const sessionData = btoa(JSON.stringify({
      github_id: user.id,
      username: user.login,
      name: user.name,
      avatar: user.avatar_url,
      token: tokenData.access_token,
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
