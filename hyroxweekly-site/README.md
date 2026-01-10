# Hyrox Weekly Website

Your complete website ready for deployment.

## 📁 Folder Structure

```
hyroxweekly-site/
├── index.html              # Homepage with hero, features, subscribe
├── archive/
│   └── index.html          # Archive listing page
│   └── edition-1-2024-12-15.html   # (Add your edition files here)
├── premium/
│   └── index.html          # Premium coming soon page
├── privacy/
│   └── index.html          # Privacy policy
├── assets/                 # (Create this for images, favicon)
│   └── favicon.svg
└── README.md               # This file
```

## 🚀 Deployment Options

### Option 1: Netlify (Recommended - Free)

1. Go to [netlify.com](https://netlify.com) and sign up
2. Click "Add new site" → "Deploy manually"
3. Drag and drop the entire `hyroxweekly-site` folder
4. Your site is live at a random URL (e.g., `amazing-name-123.netlify.app`)

**Connect your domain:**
1. Go to Site settings → Domain management
2. Click "Add custom domain"
3. Enter `hyroxweekly.com`
4. Follow DNS instructions (update nameservers or add CNAME record)

### Option 2: Vercel (Free)

1. Go to [vercel.com](https://vercel.com) and sign up
2. Click "Add New" → "Project"
3. Upload your folder or connect via GitHub
4. Add custom domain in project settings

### Option 3: GitHub Pages (Free)

1. Create a repo named `hyroxweekly.github.io` (or any name)
2. Upload all files
3. Go to Settings → Pages → Enable
4. Add custom domain

## ⚙️ Setup Checklist

### 1. Add Beehiiv Subscribe Form

Get your embed code:
1. Beehiiv → Grow → Forms
2. Create or select a form
3. Click "Embed" and copy the code

Paste it in these files (search for "BEEHIIV EMBED"):
- [ ] `index.html` (homepage hero)
- [ ] `premium/index.html` (waitlist)

### 2. Update DNS Records

Point your domain to your hosting:

**For Netlify:**
```
Type: CNAME
Name: www
Value: your-site.netlify.app

Type: A
Name: @
Value: 75.2.60.5
```

**For Vercel:**
```
Type: CNAME
Name: www
Value: cname.vercel-dns.com

Type: A
Name: @
Value: 76.76.19.19
```

### 3. Enable HTTPS

Both Netlify and Vercel provide free SSL certificates automatically.
Just make sure "Force HTTPS" is enabled in settings.

## 📝 Weekly Workflow

### Publishing a New Edition

1. **Generate in Dashboard**
   - Go to Generate page
   - Select content and click Generate
   - Go to "🌐 Website Export" tab
   - Download the HTML file

2. **Upload to Website**
   - Rename file to match pattern: `edition-X-YYYY-MM-DD.html`
   - Upload to `/archive/` folder
   - Update `archive/index.html` to add the new edition link

3. **Update Archive Page**
   
   Add a new entry in `archive/index.html`:
   ```html
   <a href="/archive/edition-2-2025-01-05.html" class="archive-item">
     <div class="archive-item-content">
       <div class="archive-item-edition">Edition #2</div>
       <h3 class="archive-item-title">December 29 - January 4, 2025</h3>
       <div class="archive-item-meta">
         <span>📹 8 videos</span>
         <span>🎙️ 3 podcasts</span>
         <span>📝 4 articles</span>
       </div>
     </div>
     <span class="archive-item-arrow">→</span>
   </a>
   ```

4. **Deploy**
   - Netlify: Drag and drop updated files, or use CLI
   - If using Git: Just push changes

## 🎨 Customization

### Colors (in CSS)
- Primary brand: `#CC5500` (orange)
- Dark background: `#1a1a1a`
- Text: `#1a1a1a` (dark), `#666` (muted)

### Fonts
Using Google Fonts "Barlow" - already loaded in all pages.

### Adding a Logo
1. Create `assets/` folder
2. Add your logo as `logo.svg` or `logo.png`
3. Replace text in nav with: `<img src="/assets/logo.svg" alt="Hyrox Weekly" height="30">`

## 📊 Analytics (Optional)

### Google Analytics
Add before `</head>` in all pages:
```html
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-XXXXXXXXXX');
</script>
```

### Plausible (Privacy-focused alternative)
```html
<script defer data-domain="hyroxweekly.com" src="https://plausible.io/js/script.js"></script>
```

## 🔗 Important Links

- Beehiiv Dashboard: https://app.beehiiv.com
- Netlify Dashboard: https://app.netlify.com
- Domain Registrar: (wherever you bought hyroxweekly.com)

## ❓ Need Help?

- Netlify Docs: https://docs.netlify.com
- Beehiiv Support: https://support.beehiiv.com
