# VirtualCarHub WordPress Production Checklist

## Upload Artifacts

- Parent theme: `wordpress/uploads/themeforest-i56dEOEz-motors-automotive-cars-vehicle-boat-dealership-classifieds-wordpress-theme/Motors/motors-5.6.91.zip`
- Child theme: `wordpress/packages/virtualcarhub-motors-child.zip`

## WordPress Setup

1. Activate parent theme once, then activate child theme.
2. Install required Motors plugins.
3. Set permalink structure to `/%postname%/`.
4. Set static front page.
5. Confirm menu locations are assigned in Motors header settings.
6. Review auto-seeded pages/menu after child theme activation.

## Content/Brand QA

1. Verify home page hero and CTA copy match VirtualCarHub language.
2. Verify mapped page slugs render VCH blueprints:
   - `/about-us/`
   - `/contact-us/`
   - `/inventory/`
   - `/financing/`
   - `/dashboard/`
   - `/admin-workspace/`
   - `/returns/`
   - `/faq/`
   - `/privacy-policy/`
   - `/terms/`
3. Verify 404 and search pages use branded templates.
4. Verify VInventory archive and VDP banner styling are active.

## Inventory Integration QA

1. Test export endpoint connectivity from Hostinger environment.
2. Run initial listing import.
3. Validate image mapping and card thumbnails.
4. Validate VDP fields reflect merged source logic.
5. Run incremental import with `updated_since`.

## Performance/Safety QA

1. Enable page caching.
2. Enable image optimization plugin.
3. Enable automated backups.
4. Ensure HTTPS and security headers.
5. Confirm admin account hardening and MFA.
