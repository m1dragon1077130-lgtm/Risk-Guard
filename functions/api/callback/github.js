export async function onRequest(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');
  
  // اگه کاربر Cancel زد
  if (error) {
    return Response.redirect(`${url.origin}/login.html?error=cancelled`, 302);
  }
  
  if (!code || !state) {
    return Response.redirect(`${url.origin}/login.html?error=invalid`, 302);
  }
  
  // چک State
  const cookies = request.headers.get('Cookie') || '';
  const savedState = cookies.match(/oauth_state=([^;]+)/)?.[1];
  
  if (savedState !== state) {
    return Response.redirect(`${url.origin}/login.html?error=csrf`, 302);
  }
  
  try {
    // ۱. code → access_token
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
      return Response.redirect(`${url.origin}/login.html?error=token_failed`, 302);
    }
    
    // ۲. کاربر رو بگیر
    const userRes = await fetch('https://api.github.com/user', {
      headers: {
        'Authorization': `token ${tokenData.access_token}`,
        'User-Agent': 'RiskGuard',
      },
    });
    
    const user = await userRes.json();
    
    // ۳. ذخیره در Session Cookie (ساده، برای شروع)
    const sessionData = btoa(JSON.stringify({
      github_id: user.id,
      username: user.login,
      name: user.name,
      avatar: user.avatar_url,
      token: tokenData.access_token,
    }));
    
    // ۴. ریدایرکت به داشبورد
    const response = Response.redirect(`${url.origin}/dashboard.html`, 302);
    
    response.headers.append(
      'Set-Cookie',
      `session=${sessionData}; HttpOnly; Secure; SameSite=Lax; Max-Age=86400; Path=/`
    );
    response.headers.append(
      'Set-Cookie',
      `oauth_state=; HttpOnly; Secure; SameSite=Lax; Max-Age=0; Path=/`
    );
    
    return response;
    
  } catch (err) {
    console.error('OAuth error:', err);
    return Response.redirect(`${url.origin}/login.html?error=server`, 302);
  }
}
