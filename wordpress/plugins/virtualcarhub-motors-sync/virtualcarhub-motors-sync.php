<?php
/**
 * Plugin Name: VirtualCarHub Motors Sync
 * Description: Sync VirtualCarHub inventory API listings into Motors listing posts with image and attribute mapping.
 * Version: 0.1.22
 * Author: VirtualCarHub
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'VCH_MOTORS_SYNC_VERSION', '0.1.22' );
define( 'VCH_MOTORS_SYNC_SETTINGS_OPTION', 'vch_motors_sync_settings' );
define( 'VCH_MOTORS_SYNC_STATE_OPTION', 'vch_motors_sync_state' );
define( 'VCH_MOTORS_SYNC_LAST_SYNC_OPTION', 'vch_motors_sync_last_synced_at' );
define( 'VCH_MOTORS_SYNC_LAST_TEST_OPTION', 'vch_motors_sync_last_test_result' );
define( 'VCH_MOTORS_SYNC_CRON_HOOK', 'vch_motors_sync_run_event' );
define( 'VCH_MOTORS_SYNC_NONCE_ACTION', 'vch_motors_sync_now' );
define( 'VCH_MOTORS_SYNC_NONCE_NAME', 'vch_motors_sync_nonce' );
define( 'VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET', 45 );
define( 'VCH_MOTORS_SYNC_MAX_ERROR_SNIPPET', 280 );
define( 'VCH_MOTORS_SYNC_DEFAULT_EXPORT_ENDPOINT', 'https://app.virtualcarhub.com/v1/inventory/wordpress/export' );
define( 'VCH_MOTORS_SYNC_DEFAULT_IMAGE_DOWNLOAD_TIMEOUT_SEC', 45 );
define( 'VCH_MOTORS_SYNC_DEFAULT_MAX_IMAGES_PER_LISTING', 0 ); // 0 = sync all images.
define( 'VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL', 'external_urls' );
define( 'VCH_MOTORS_SYNC_IMAGE_MODE_FEATURED', 'download_featured_only' );
define( 'VCH_MOTORS_SYNC_IMAGE_MODE_ALL', 'download_all' );
define( 'VCH_MOTORS_SYNC_LIVE_TOPUP_MIN_RESULTS', 35 );
define( 'VCH_MOTORS_SYNC_LIVE_TOPUP_LIMIT', 200 );
define( 'VCH_MOTORS_SYNC_LIVE_TOPUP_CACHE_TTL', 180 );

function vch_motors_sync_normalize_export_endpoint( $endpoint ) {
	$value = trim( (string) $endpoint );
	if ( '' === $value ) {
		return VCH_MOTORS_SYNC_DEFAULT_EXPORT_ENDPOINT;
	}

	$legacy_endpoints = array(
		'https://virtualcarhub.com/api/vch/inventory/wordpress/export',
		'http://virtualcarhub.com/api/vch/inventory/wordpress/export',
		'https://app.virtualcrhub.com/v1/inventory/wordpress/export',
		'http://app.virtualcrhub.com/v1/inventory/wordpress/export',
	);
	if ( in_array( $value, $legacy_endpoints, true ) ) {
		return VCH_MOTORS_SYNC_DEFAULT_EXPORT_ENDPOINT;
	}

	return $value;
}

function vch_motors_sync_default_settings() {
	return array(
		'export_endpoint'     => VCH_MOTORS_SYNC_DEFAULT_EXPORT_ENDPOINT,
		'auth_bearer_token'   => '',
		'post_type'           => 'listings',
		'per_page'            => 100,
		'max_pages'           => 10,
		'include_price_stats' => 0,
		'download_images'     => 1,
		'image_mode'          => VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL,
		'image_download_timeout_sec' => VCH_MOTORS_SYNC_DEFAULT_IMAGE_DOWNLOAD_TIMEOUT_SEC,
		'max_images_per_listing'     => VCH_MOTORS_SYNC_DEFAULT_MAX_IMAGES_PER_LISTING,
		'cron_interval'       => 'hourly',
	);
}

function vch_motors_sync_get_settings() {
	$saved    = get_option( VCH_MOTORS_SYNC_SETTINGS_OPTION, array() );
	$defaults = vch_motors_sync_default_settings();
	if ( ! is_array( $saved ) ) {
		$saved = array();
	}

	$settings = wp_parse_args( $saved, $defaults );
	$normalized_endpoint = vch_motors_sync_normalize_export_endpoint( $settings['export_endpoint'] ?? '' );
	if ( (string) ( $settings['export_endpoint'] ?? '' ) !== $normalized_endpoint ) {
		$settings['export_endpoint'] = $normalized_endpoint;
		// Persist migration so next loads use the corrected endpoint.
		update_option( VCH_MOTORS_SYNC_SETTINGS_OPTION, $settings, false );
	}

	return $settings;
}

function vch_motors_sync_sanitize_settings( $input ) {
	$defaults = vch_motors_sync_default_settings();
	if ( ! is_array( $input ) ) {
		$input = array();
	}

	$settings                         = $defaults;
	$settings['export_endpoint']      = esc_url_raw( vch_motors_sync_normalize_export_endpoint( (string) ( $input['export_endpoint'] ?? $defaults['export_endpoint'] ) ) );
	$settings['auth_bearer_token']    = trim( (string) ( $input['auth_bearer_token'] ?? '' ) );
	$settings['post_type']            = sanitize_key( (string) ( $input['post_type'] ?? $defaults['post_type'] ) );
	$settings['per_page']             = min( 500, max( 1, absint( $input['per_page'] ?? $defaults['per_page'] ) ) );
	$settings['max_pages']            = min( 100, max( 1, absint( $input['max_pages'] ?? $defaults['max_pages'] ) ) );
	$settings['include_price_stats']  = empty( $input['include_price_stats'] ) ? 0 : 1;
	$settings['download_images']      = empty( $input['download_images'] ) ? 0 : 1;
	$mode_candidate = sanitize_key( (string) ( $input['image_mode'] ?? '' ) );
	$allowed_modes  = array(
		VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL,
		VCH_MOTORS_SYNC_IMAGE_MODE_FEATURED,
		VCH_MOTORS_SYNC_IMAGE_MODE_ALL,
	);
	if ( in_array( $mode_candidate, $allowed_modes, true ) ) {
		$settings['image_mode'] = $mode_candidate;
	} else {
		// Backward compatibility: prior versions only had a download_images boolean.
		$settings['image_mode'] = empty( $settings['download_images'] )
			? VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL
			: VCH_MOTORS_SYNC_IMAGE_MODE_ALL;
	}
	$settings['image_download_timeout_sec'] = min(
		300,
		max(
			5,
			absint( $input['image_download_timeout_sec'] ?? $defaults['image_download_timeout_sec'] )
		)
	);
	$settings['max_images_per_listing'] = min(
		1000,
		max(
			0,
			absint( $input['max_images_per_listing'] ?? $defaults['max_images_per_listing'] )
		)
	);
	$allowed_intervals                = array( 'fifteen_minutes', 'hourly', 'twicedaily', 'daily' );
	$settings['cron_interval']        = in_array( $input['cron_interval'] ?? '', $allowed_intervals, true )
		? $input['cron_interval']
		: $defaults['cron_interval'];

	if ( empty( $settings['export_endpoint'] ) ) {
		$settings['export_endpoint'] = VCH_MOTORS_SYNC_DEFAULT_EXPORT_ENDPOINT;
	}
	if ( empty( $settings['post_type'] ) ) {
		$settings['post_type'] = $defaults['post_type'];
	}

	return $settings;
}

function vch_motors_sync_add_intervals( $schedules ) {
	if ( ! isset( $schedules['fifteen_minutes'] ) ) {
		$schedules['fifteen_minutes'] = array(
			'interval' => 15 * MINUTE_IN_SECONDS,
			'display'  => __( 'Every 15 Minutes', 'virtualcarhub-motors-sync' ),
		);
	}

	return $schedules;
}
add_filter( 'cron_schedules', 'vch_motors_sync_add_intervals' );

function vch_motors_sync_get_schedule() {
	$settings = vch_motors_sync_get_settings();

	return $settings['cron_interval'] ?: 'hourly';
}

function vch_motors_sync_schedule_event() {
	if ( wp_next_scheduled( VCH_MOTORS_SYNC_CRON_HOOK ) ) {
		return;
	}

	wp_schedule_event( time() + 60, vch_motors_sync_get_schedule(), VCH_MOTORS_SYNC_CRON_HOOK );
}

function vch_motors_sync_reschedule_event() {
	$next = wp_next_scheduled( VCH_MOTORS_SYNC_CRON_HOOK );
	if ( $next ) {
		wp_unschedule_event( $next, VCH_MOTORS_SYNC_CRON_HOOK );
	}
	vch_motors_sync_schedule_event();
}

function vch_motors_sync_activate() {
	if ( false === get_option( VCH_MOTORS_SYNC_SETTINGS_OPTION, false ) ) {
		add_option( VCH_MOTORS_SYNC_SETTINGS_OPTION, vch_motors_sync_default_settings(), '', false );
	}
	vch_motors_sync_schedule_event();
}
register_activation_hook( __FILE__, 'vch_motors_sync_activate' );

function vch_motors_sync_deactivate() {
	$next = wp_next_scheduled( VCH_MOTORS_SYNC_CRON_HOOK );
	if ( $next ) {
		wp_unschedule_event( $next, VCH_MOTORS_SYNC_CRON_HOOK );
	}
}
register_deactivation_hook( __FILE__, 'vch_motors_sync_deactivate' );

function vch_motors_sync_on_settings_update( $old_value, $value ) {
	if ( $old_value === $value ) {
		return;
	}
	vch_motors_sync_reschedule_event();
}
add_action( 'update_option_' . VCH_MOTORS_SYNC_SETTINGS_OPTION, 'vch_motors_sync_on_settings_update', 10, 2 );

function vch_motors_sync_register_settings() {
	register_setting(
		'vch_motors_sync_group',
		VCH_MOTORS_SYNC_SETTINGS_OPTION,
		array(
			'type'              => 'array',
			'sanitize_callback' => 'vch_motors_sync_sanitize_settings',
		)
	);
}
add_action( 'admin_init', 'vch_motors_sync_register_settings' );

function vch_motors_sync_admin_menu() {
	add_submenu_page(
		'tools.php',
		__( 'VCH Motors Sync', 'virtualcarhub-motors-sync' ),
		__( 'VCH Motors Sync', 'virtualcarhub-motors-sync' ),
		'manage_options',
		'vch-motors-sync',
		'vch_motors_sync_render_admin_page'
	);
}
add_action( 'admin_menu', 'vch_motors_sync_admin_menu' );

function vch_motors_sync_render_admin_page() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}

	$settings = vch_motors_sync_get_settings();
	$state    = get_option( VCH_MOTORS_SYNC_STATE_OPTION, array() );
	$last     = get_option( VCH_MOTORS_SYNC_LAST_SYNC_OPTION, '' );
	$last_test = get_option( VCH_MOTORS_SYNC_LAST_TEST_OPTION, array() );
	$status   = sanitize_text_field( $_GET['vch_sync_status'] ?? '' );
	$action   = sanitize_text_field( $_GET['vch_sync_action'] ?? 'sync' );
	$count    = absint( $_GET['vch_sync_count'] ?? 0 );
	?>
	<div class="wrap">
		<h1><?php esc_html_e( 'VirtualCarHub Motors Sync', 'virtualcarhub-motors-sync' ); ?></h1>
		<p><?php esc_html_e( 'Sync VirtualCarHub inventory export into Motors listing posts.', 'virtualcarhub-motors-sync' ); ?></p>

		<?php if ( 'ok' === $status ) : ?>
			<div class="notice notice-success">
				<p>
					<?php
					if ( 'force' === $action ) {
						esc_html_e( 'Forced full sync completed.', 'virtualcarhub-motors-sync' );
					} elseif ( 'clean' === $action ) {
						echo esc_html(
							sprintf(
								/* translators: %d: listing count */
								__( 'Cleanup completed. Drafted %d non-synced listing(s).', 'virtualcarhub-motors-sync' ),
								(int) $count
							)
						);
					} elseif ( 'purge_terms' === $action ) {
						echo esc_html(
							sprintf(
								/* translators: %d: term count */
								__( 'Purge completed. Removed %d empty filter term(s).', 'virtualcarhub-motors-sync' ),
								(int) $count
							)
						);
					} elseif ( 'test' === $action ) {
						esc_html_e( 'Connection test succeeded.', 'virtualcarhub-motors-sync' );
					} else {
						esc_html_e( 'Manual sync completed.', 'virtualcarhub-motors-sync' );
					}
					?>
				</p>
			</div>
		<?php elseif ( 'error' === $status ) : ?>
			<div class="notice notice-error">
				<p>
					<?php
					if ( 'force' === $action ) {
						esc_html_e( 'Forced full sync failed. Check Last Sync State below.', 'virtualcarhub-motors-sync' );
					} elseif ( 'clean' === $action ) {
						esc_html_e( 'Cleanup failed. Non-synced listings were not drafted.', 'virtualcarhub-motors-sync' );
					} elseif ( 'purge_terms' === $action ) {
						esc_html_e( 'Purge failed. Empty filter terms were not removed.', 'virtualcarhub-motors-sync' );
					} elseif ( 'test' === $action ) {
						esc_html_e( 'Connection test failed. Check Last Connection Test below.', 'virtualcarhub-motors-sync' );
					} else {
						esc_html_e( 'Manual sync failed. Check Last Sync State below.', 'virtualcarhub-motors-sync' );
					}
					?>
				</p>
			</div>
		<?php endif; ?>

		<form method="post" action="options.php">
			<?php settings_fields( 'vch_motors_sync_group' ); ?>
			<table class="form-table" role="presentation">
				<tr>
					<th scope="row"><label for="vch_export_endpoint"><?php esc_html_e( 'Export Endpoint', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td><input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[export_endpoint]" id="vch_export_endpoint" type="url" class="regular-text code" value="<?php echo esc_attr( $settings['export_endpoint'] ); ?>"></td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_auth_bearer"><?php esc_html_e( 'Bearer Token', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td>
						<input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[auth_bearer_token]" id="vch_auth_bearer" type="password" class="regular-text code" value="<?php echo esc_attr( $settings['auth_bearer_token'] ); ?>">
						<p class="description"><?php esc_html_e( 'Required only if backend WORDPRESS_EXPORT_BEARER_TOKEN is set.', 'virtualcarhub-motors-sync' ); ?></p>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_post_type"><?php esc_html_e( 'Listing Post Type', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td><input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[post_type]" id="vch_post_type" type="text" class="regular-text code" value="<?php echo esc_attr( $settings['post_type'] ); ?>"></td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_per_page"><?php esc_html_e( 'Rows Per Page', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td><input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[per_page]" id="vch_per_page" type="number" min="1" max="500" value="<?php echo esc_attr( (string) $settings['per_page'] ); ?>"></td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_max_pages"><?php esc_html_e( 'Max Pages Per Run', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td><input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[max_pages]" id="vch_max_pages" type="number" min="1" max="100" value="<?php echo esc_attr( (string) $settings['max_pages'] ); ?>"></td>
				</tr>
				<tr>
					<th scope="row"><?php esc_html_e( 'Include MarketCheck Price Stats', 'virtualcarhub-motors-sync' ); ?></th>
					<td><label><input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[include_price_stats]" type="checkbox" value="1" <?php checked( ! empty( $settings['include_price_stats'] ) ); ?>> <?php esc_html_e( 'Fetch market retail comparison fields during sync', 'virtualcarhub-motors-sync' ); ?></label></td>
				</tr>
				<tr>
					<th scope="row"><?php esc_html_e( 'Download and Attach Images', 'virtualcarhub-motors-sync' ); ?></th>
					<td><label><input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[download_images]" type="checkbox" value="1" <?php checked( ! empty( $settings['download_images'] ) ); ?>> <?php esc_html_e( 'Sync featured image and gallery from API image URLs', 'virtualcarhub-motors-sync' ); ?></label></td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_image_mode"><?php esc_html_e( 'Image Sync Mode', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td>
						<select name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[image_mode]" id="vch_image_mode">
							<option value="<?php echo esc_attr( VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL ); ?>" <?php selected( $settings['image_mode'], VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL ); ?>><?php esc_html_e( 'External URLs only (fastest)', 'virtualcarhub-motors-sync' ); ?></option>
							<option value="<?php echo esc_attr( VCH_MOTORS_SYNC_IMAGE_MODE_FEATURED ); ?>" <?php selected( $settings['image_mode'], VCH_MOTORS_SYNC_IMAGE_MODE_FEATURED ); ?>><?php esc_html_e( 'Download featured image only', 'virtualcarhub-motors-sync' ); ?></option>
							<option value="<?php echo esc_attr( VCH_MOTORS_SYNC_IMAGE_MODE_ALL ); ?>" <?php selected( $settings['image_mode'], VCH_MOTORS_SYNC_IMAGE_MODE_ALL ); ?>><?php esc_html_e( 'Download featured + gallery', 'virtualcarhub-motors-sync' ); ?></option>
						</select>
						<p class="description"><?php esc_html_e( 'Use External URLs for scale: no per-listing media downloads during sync.', 'virtualcarhub-motors-sync' ); ?></p>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_image_download_timeout_sec"><?php esc_html_e( 'Image Download Timeout (sec)', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td>
						<input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[image_download_timeout_sec]" id="vch_image_download_timeout_sec" type="number" min="5" max="300" value="<?php echo esc_attr( (string) $settings['image_download_timeout_sec'] ); ?>">
						<p class="description"><?php esc_html_e( 'Per-image timeout when sideloading into WordPress media library.', 'virtualcarhub-motors-sync' ); ?></p>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_max_images_per_listing"><?php esc_html_e( 'Max Images Per Listing', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td>
						<input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[max_images_per_listing]" id="vch_max_images_per_listing" type="number" min="0" max="1000" value="<?php echo esc_attr( (string) $settings['max_images_per_listing'] ); ?>">
						<p class="description"><?php esc_html_e( 'Set 0 to sync all images from the API response.', 'virtualcarhub-motors-sync' ); ?></p>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="vch_cron_interval"><?php esc_html_e( 'Cron Interval', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td>
						<select name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[cron_interval]" id="vch_cron_interval">
							<option value="fifteen_minutes" <?php selected( $settings['cron_interval'], 'fifteen_minutes' ); ?>><?php esc_html_e( 'Every 15 minutes', 'virtualcarhub-motors-sync' ); ?></option>
							<option value="hourly" <?php selected( $settings['cron_interval'], 'hourly' ); ?>><?php esc_html_e( 'Hourly', 'virtualcarhub-motors-sync' ); ?></option>
							<option value="twicedaily" <?php selected( $settings['cron_interval'], 'twicedaily' ); ?>><?php esc_html_e( 'Twice Daily', 'virtualcarhub-motors-sync' ); ?></option>
							<option value="daily" <?php selected( $settings['cron_interval'], 'daily' ); ?>><?php esc_html_e( 'Daily', 'virtualcarhub-motors-sync' ); ?></option>
						</select>
					</td>
				</tr>
			</table>
			<p><strong><?php esc_html_e( 'Hard rule:', 'virtualcarhub-motors-sync' ); ?></strong> <?php echo esc_html( sprintf( 'Only vehicles with Days on Market >= %d are eligible for publish.', (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET ) ); ?></p>
			<?php submit_button( __( 'Save Sync Settings', 'virtualcarhub-motors-sync' ) ); ?>
		</form>

		<hr>
		<h2><?php esc_html_e( 'Run Manual Sync', 'virtualcarhub-motors-sync' ); ?></h2>
		<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
			<input type="hidden" name="action" value="vch_motors_sync_now">
			<?php wp_nonce_field( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME ); ?>
			<?php submit_button( __( 'Sync Now', 'virtualcarhub-motors-sync' ), 'secondary' ); ?>
		</form>

		<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px;">
			<input type="hidden" name="action" value="vch_motors_sync_force_full_sync">
			<?php wp_nonce_field( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME ); ?>
			<?php submit_button( __( 'Force Full Sync (Reset Checkpoint)', 'virtualcarhub-motors-sync' ), 'secondary' ); ?>
		</form>

		<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px;">
			<input type="hidden" name="action" value="vch_motors_sync_test_connection">
			<?php wp_nonce_field( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME ); ?>
			<?php submit_button( __( 'Test API Connection', 'virtualcarhub-motors-sync' ), 'secondary' ); ?>
		</form>

		<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px;">
			<input type="hidden" name="action" value="vch_motors_sync_cleanup_non_synced_listings">
			<?php wp_nonce_field( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME ); ?>
			<?php submit_button( __( 'Draft Non-Synced Listings', 'virtualcarhub-motors-sync' ), 'secondary' ); ?>
		</form>

		<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="margin-top:12px;">
			<input type="hidden" name="action" value="vch_motors_sync_purge_empty_terms">
			<?php wp_nonce_field( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME ); ?>
			<?php submit_button( __( 'Purge Empty Filter Terms', 'virtualcarhub-motors-sync' ), 'secondary' ); ?>
		</form>

		<hr>
		<h2><?php esc_html_e( 'Sync State', 'virtualcarhub-motors-sync' ); ?></h2>
		<p><strong><?php esc_html_e( 'Last updated_since checkpoint:', 'virtualcarhub-motors-sync' ); ?></strong> <code><?php echo esc_html( $last ?: 'n/a' ); ?></code></p>
		<pre style="background:#fff;border:1px solid #ccd0d4;padding:12px;max-height:360px;overflow:auto;"><?php echo esc_html( wp_json_encode( $state, JSON_PRETTY_PRINT ) ); ?></pre>

		<hr>
		<h2><?php esc_html_e( 'Last Connection Test', 'virtualcarhub-motors-sync' ); ?></h2>
		<pre style="background:#fff;border:1px solid #ccd0d4;padding:12px;max-height:220px;overflow:auto;"><?php echo esc_html( wp_json_encode( $last_test, JSON_PRETTY_PRINT ) ); ?></pre>
	</div>
	<?php
}

function vch_motors_sync_admin_redirect( $status, $action, $extra = array() ) {
	$args = array_merge(
		array(
			'page'            => 'vch-motors-sync',
			'vch_sync_status' => $status,
			'vch_sync_action' => $action,
		),
		is_array( $extra ) ? $extra : array()
	);

	wp_safe_redirect(
		add_query_arg(
			$args,
			admin_url( 'tools.php' )
		)
	);
	exit;
}

function vch_motors_sync_handle_manual_sync() {
	if ( ! current_user_can( 'manage_options' ) ) {
		wp_die( esc_html__( 'Insufficient permissions.', 'virtualcarhub-motors-sync' ) );
	}

	check_admin_referer( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME );

	$result = vch_motors_sync_run( 'manual' );
	$status = is_wp_error( $result ) ? 'error' : 'ok';
	vch_motors_sync_admin_redirect( $status, 'sync' );
}
add_action( 'admin_post_vch_motors_sync_now', 'vch_motors_sync_handle_manual_sync' );

function vch_motors_sync_handle_force_full_sync() {
	if ( ! current_user_can( 'manage_options' ) ) {
		wp_die( esc_html__( 'Insufficient permissions.', 'virtualcarhub-motors-sync' ) );
	}

	check_admin_referer( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME );

	update_option( VCH_MOTORS_SYNC_LAST_SYNC_OPTION, '', false );
	$result = vch_motors_sync_run( 'manual-force-full' );
	$status = is_wp_error( $result ) ? 'error' : 'ok';
	vch_motors_sync_admin_redirect( $status, 'force' );
}
add_action( 'admin_post_vch_motors_sync_force_full_sync', 'vch_motors_sync_handle_force_full_sync' );

function vch_motors_sync_handle_test_connection() {
	if ( ! current_user_can( 'manage_options' ) ) {
		wp_die( esc_html__( 'Insufficient permissions.', 'virtualcarhub-motors-sync' ) );
	}

	check_admin_referer( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME );

	$settings = vch_motors_sync_get_settings();
	$result   = vch_motors_sync_fetch_export_page( $settings, 1, '' );
	$state    = array(
		'tested_at' => gmdate( 'c' ),
		'endpoint'  => $settings['export_endpoint'],
		'success'   => false,
	);

	if ( is_wp_error( $result ) ) {
		$state['error'] = $result->get_error_message();
		update_option( VCH_MOTORS_SYNC_LAST_TEST_OPTION, $state, false );
		vch_motors_sync_admin_redirect( 'error', 'test' );
	}

	$items      = is_array( $result['items'] ?? null ) ? $result['items'] : array();
	$pagination = is_array( $result['pagination'] ?? null ) ? $result['pagination'] : array();
	$state['success'] = true;
	$state['items_on_first_page'] = count( $items );
	$state['has_next'] = ! empty( $pagination['has_next'] );
	$state['first_vin'] = ! empty( $items[0]['vin'] ) ? $items[0]['vin'] : null;
	update_option( VCH_MOTORS_SYNC_LAST_TEST_OPTION, $state, false );
	vch_motors_sync_admin_redirect( 'ok', 'test' );
}
add_action( 'admin_post_vch_motors_sync_test_connection', 'vch_motors_sync_handle_test_connection' );

function vch_motors_sync_draft_non_synced_listings( $post_type ) {
	$total_drafted = 0;
	$batch_size    = 200;

	for ( $guard = 0; $guard < 1000; $guard++ ) {
		$posts = get_posts(
			array(
				'post_type'      => $post_type,
				'post_status'    => array( 'publish', 'pending', 'private' ),
				'posts_per_page' => $batch_size,
				'orderby'        => 'ID',
				'order'          => 'ASC',
				'fields'         => 'ids',
				'meta_query'     => array(
					'relation' => 'OR',
					array(
						'key'     => 'vch_external_id',
						'compare' => 'NOT EXISTS',
					),
					array(
						'key'     => 'vch_external_id',
						'value'   => '',
						'compare' => '=',
					),
				),
			)
		);

		if ( empty( $posts ) ) {
			break;
		}

		foreach ( $posts as $post_id ) {
			$updated = wp_update_post(
				array(
					'ID'          => (int) $post_id,
					'post_status' => 'draft',
				),
				true
			);
			if ( ! is_wp_error( $updated ) ) {
				$total_drafted++;
			}
		}
	}

	return $total_drafted;
}

function vch_motors_sync_handle_cleanup_non_synced_listings() {
	if ( ! current_user_can( 'manage_options' ) ) {
		wp_die( esc_html__( 'Insufficient permissions.', 'virtualcarhub-motors-sync' ) );
	}

	check_admin_referer( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME );

	$settings  = vch_motors_sync_get_settings();
	$post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	if ( empty( $post_type ) ) {
		$post_type = 'listings';
	}

	$count = vch_motors_sync_draft_non_synced_listings( $post_type );
	vch_motors_sync_admin_redirect(
		'ok',
		'clean',
		array(
			'vch_sync_count' => (int) $count,
		)
	);
}
add_action( 'admin_post_vch_motors_sync_cleanup_non_synced_listings', 'vch_motors_sync_handle_cleanup_non_synced_listings' );

function vch_motors_sync_purge_empty_filter_terms( $post_type ) {
	$filter_options = get_option( 'stm_vehicle_listing_options', array() );
	if ( 'listings' !== $post_type ) {
		$custom_options = get_option( "stm_{$post_type}_options", array() );
		if ( is_array( $custom_options ) && ! empty( $custom_options ) ) {
			$filter_options = $custom_options;
		}
	}
	if ( ! is_array( $filter_options ) ) {
		return 0;
	}

	$purged = 0;
	foreach ( $filter_options as $filter_option ) {
		$slug = sanitize_key( (string) ( $filter_option['slug'] ?? '' ) );
		if ( '' === $slug || ! taxonomy_exists( $slug ) ) {
			continue;
		}
		$term_ids = get_terms(
			array(
				'taxonomy'   => $slug,
				'hide_empty' => false,
				'fields'     => 'ids',
			)
		);
		if ( is_wp_error( $term_ids ) || empty( $term_ids ) ) {
			continue;
		}
		foreach ( $term_ids as $term_id ) {
			$term = get_term( (int) $term_id, $slug );
			if ( ! $term || is_wp_error( $term ) ) {
				continue;
			}
			if ( (int) $term->count > 0 ) {
				continue;
			}
			$deleted = wp_delete_term( (int) $term_id, $slug );
			if ( ! is_wp_error( $deleted ) && ! empty( $deleted ) ) {
				$purged++;
			}
		}
	}
	return $purged;
}

function vch_motors_sync_handle_purge_empty_terms() {
	if ( ! current_user_can( 'manage_options' ) ) {
		wp_die( esc_html__( 'Insufficient permissions.', 'virtualcarhub-motors-sync' ) );
	}

	check_admin_referer( VCH_MOTORS_SYNC_NONCE_ACTION, VCH_MOTORS_SYNC_NONCE_NAME );

	$settings  = vch_motors_sync_get_settings();
	$post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	if ( empty( $post_type ) ) {
		$post_type = 'listings';
	}

	$count = vch_motors_sync_purge_empty_filter_terms( $post_type );
	vch_motors_sync_admin_redirect(
		'ok',
		'purge_terms',
		array(
			'vch_sync_count' => (int) $count,
		)
	);
}
add_action( 'admin_post_vch_motors_sync_purge_empty_terms', 'vch_motors_sync_handle_purge_empty_terms' );

function vch_motors_sync_get_image_mode( $settings ) {
	$mode = sanitize_key( (string) ( $settings['image_mode'] ?? '' ) );
	$allowed_modes = array(
		VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL,
		VCH_MOTORS_SYNC_IMAGE_MODE_FEATURED,
		VCH_MOTORS_SYNC_IMAGE_MODE_ALL,
	);

	if ( in_array( $mode, $allowed_modes, true ) ) {
		return $mode;
	}

	return empty( $settings['download_images'] )
		? VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL
		: VCH_MOTORS_SYNC_IMAGE_MODE_ALL;
}

function vch_motors_sync_run_cron() {
	vch_motors_sync_run( 'cron' );
}
add_action( VCH_MOTORS_SYNC_CRON_HOOK, 'vch_motors_sync_run_cron' );

function vch_motors_sync_query_targets_post_type( $query, $target_post_type ) {
	$post_type = $query->get( 'post_type' );
	$matches   = false;
	if ( is_array( $post_type ) ) {
		$matches = in_array( $target_post_type, $post_type, true );
	} elseif ( is_string( $post_type ) ) {
		$matches = $target_post_type === $post_type;
	}

	if ( ! $matches && $query->is_post_type_archive( $target_post_type ) ) {
		$matches = true;
	}

	return $matches;
}

function vch_motors_sync_request_value( $keys ) {
	if ( ! is_array( $keys ) ) {
		return '';
	}
	foreach ( $keys as $key ) {
		if ( ! is_string( $key ) || '' === $key ) {
			continue;
		}
		if ( ! isset( $_REQUEST[ $key ] ) ) {
			continue;
		}
		$value = sanitize_text_field( wp_unslash( (string) $_REQUEST[ $key ] ) );
		if ( '' !== trim( $value ) ) {
			return trim( $value );
		}
	}
	return '';
}

function vch_motors_sync_request_zip() {
	$raw = vch_motors_sync_request_value(
		array(
			'zip_code',
			'zipcode',
			'zip',
			'postal_code',
			'postal-code',
			'zip-code',
			'location',
			'ca-location',
		)
	);
	if ( '' === $raw ) {
		return '';
	}
	$digits = preg_replace( '/[^0-9]/', '', $raw );
	if ( strlen( $digits ) < 5 ) {
		return '';
	}
	return substr( $digits, 0, 5 );
}

function vch_motors_sync_request_radius() {
	$raw = vch_motors_sync_request_value(
		array(
			'radius',
			'distance',
			'miles',
			'max_dist',
			'miles-away',
			'max-distance',
			'search_radius',
		)
	);
	$radius = absint( $raw );
	if ( $radius <= 0 ) {
		$radius = 50;
	}
	return min( 500, max( 1, $radius ) );
}

function vch_motors_sync_build_live_api_query_from_request( $settings, $zip ) {
	$api_query = array(
		'zip_code'           => trim( (string) $zip ),
		'radius'             => (string) vch_motors_sync_request_radius(),
		'topup_if_below'     => (string) (int) VCH_MOTORS_SYNC_LIVE_TOPUP_MIN_RESULTS,
		'topup_limit'        => (string) (int) VCH_MOTORS_SYNC_LIVE_TOPUP_LIMIT,
		'include_unavailable'=> 'true',
		'has_images'         => 'true',
		'min_dom'            => (string) (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET,
		'sort_by'            => 'updated_at',
		'sort_dir'           => 'desc',
		'per_page'           => (string) min( 100, max( 25, (int) ( $settings['per_page'] ?? 100 ) ) ),
	);
	$q = vch_motors_sync_request_value( array( 'q', 's' ) );
	if ( '' !== $q ) {
		$api_query['q'] = $q;
	}
	$make = vch_motors_sync_request_value( array( 'make' ) );
	if ( '' !== $make ) {
		$api_query['make'] = $make;
	}
	$model = vch_motors_sync_request_value( array( 'model', 'serie' ) );
	if ( '' !== $model ) {
		$api_query['model'] = $model;
	}
	$trim = vch_motors_sync_request_value( array( 'trim', 'trim_level', 'trim-level' ) );
	if ( '' !== $trim ) {
		$api_query['trim'] = $trim;
	}
	$body_type = vch_motors_sync_request_value( array( 'body_type', 'body' ) );
	if ( '' !== $body_type ) {
		$api_query['body_type'] = $body_type;
	}
	$state = strtoupper( vch_motors_sync_request_value( array( 'state' ) ) );
	if ( strlen( $state ) === 2 ) {
		$api_query['state'] = $state;
	}
	$condition = strtolower( vch_motors_sync_request_value( array( 'condition', 'type', 'inventory_type' ) ) );
	if ( '' !== $condition ) {
		if ( false !== strpos( $condition, 'new' ) ) {
			$api_query['inventory_type'] = 'new';
		} elseif ( false !== strpos( $condition, 'used' ) || false !== strpos( $condition, 'cert' ) ) {
			$api_query['inventory_type'] = 'used';
		}
	}
	$year = absint( vch_motors_sync_request_value( array( 'year', 'ca-year' ) ) );
	if ( $year > 1900 && $year < 2100 ) {
		$api_query['min_year'] = (string) $year;
		$api_query['max_year'] = (string) $year;
	}
	$min_price = vch_motors_sync_request_value( array( 'min_price', 'price_from', 'price-from' ) );
	if ( '' !== $min_price && is_numeric( $min_price ) ) {
		$api_query['min_price'] = (string) (float) $min_price;
	}
	$max_price = vch_motors_sync_request_value( array( 'max_price', 'price_to', 'price-to', 'price' ) );
	if ( '' !== $max_price && is_numeric( $max_price ) ) {
		$api_query['max_price'] = (string) (float) $max_price;
	}

	return $api_query;
}

function vch_motors_sync_live_seed_cache_key( $api_query ) {
	return 'vch_live_seed_' . md5( wp_json_encode( $api_query ) ?: '' );
}

function vch_motors_sync_maybe_seed_inventory_from_request( $query ) {
	static $running = false;

	if ( $running ) {
		return;
	}
	if ( ! ( $query instanceof WP_Query ) ) {
		return;
	}
	if ( is_admin() && ! wp_doing_ajax() ) {
		return;
	}

	$settings         = vch_motors_sync_get_settings();
	$target_post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	if ( empty( $target_post_type ) ) {
		$target_post_type = 'listings';
	}
	if ( ! vch_motors_sync_query_targets_post_type( $query, $target_post_type ) ) {
		return;
	}

	$zip = vch_motors_sync_request_zip();
	if ( '' === $zip ) {
		return;
	}

	$api_query = vch_motors_sync_build_live_api_query_from_request( $settings, $zip );
	$cache_key = vch_motors_sync_live_seed_cache_key( $api_query );
	if ( get_transient( $cache_key ) ) {
		return;
	}
	set_transient( $cache_key, gmdate( 'c' ), (int) VCH_MOTORS_SYNC_LIVE_TOPUP_CACHE_TTL );

	$running = true;
	$seeded_vins = array();
	for ( $page = 1; $page <= 3; $page++ ) {
		$page_result = vch_motors_sync_fetch_export_page( $settings, $page, '', $api_query );
		if ( is_wp_error( $page_result ) ) {
			break;
		}
		$items = is_array( $page_result['items'] ?? null ) ? $page_result['items'] : array();
		foreach ( $items as $item ) {
			$vin = strtoupper( trim( (string) ( $item['vin'] ?? '' ) ) );
			if ( 17 !== strlen( $vin ) ) {
				continue;
			}
			$dom_value = vch_motors_sync_to_int( $item['days_on_market'] ?? null );
			if ( null === $dom_value || $dom_value < (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET ) {
				continue;
			}
			$seeded_vins[] = $vin;
			vch_motors_sync_upsert_listing( $item, $settings );
		}
		$pagination = is_array( $page_result['pagination'] ?? null ) ? $page_result['pagination'] : array();
		if ( empty( $pagination['has_next'] ) ) {
			break;
		}
	}
	if ( ! empty( $seeded_vins ) ) {
		set_transient(
			$cache_key . '_vins',
			array_values( array_unique( $seeded_vins ) ),
			(int) VCH_MOTORS_SYNC_LIVE_TOPUP_CACHE_TTL
		);
	}
	$running = false;
}
add_action( 'pre_get_posts', 'vch_motors_sync_maybe_seed_inventory_from_request', 12 );

function vch_motors_sync_apply_dom_floor_to_listing_queries( $query ) {
	if ( ! ( $query instanceof WP_Query ) ) {
		return;
	}

	if ( is_admin() && ! wp_doing_ajax() ) {
		return;
	}

	$settings         = vch_motors_sync_get_settings();
	$target_post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	if ( empty( $target_post_type ) ) {
		$target_post_type = 'listings';
	}
	if ( ! vch_motors_sync_query_targets_post_type( $query, $target_post_type ) ) {
		return;
	}

	$meta_query   = $query->get( 'meta_query' );
	$meta_query   = is_array( $meta_query ) ? $meta_query : array();
	$meta_query[] = array(
		'key'     => 'vch_external_id',
		'compare' => 'EXISTS',
	);
	$meta_query[] = array(
		'key'     => 'vch_days_on_market',
		'value'   => (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET,
		'compare' => '>=',
		'type'    => 'NUMERIC',
	);
	$zip_filter = vch_motors_sync_request_zip();
	if ( '' !== $zip_filter ) {
		$api_query = vch_motors_sync_build_live_api_query_from_request( $settings, $zip_filter );
		$cache_key = vch_motors_sync_live_seed_cache_key( $api_query ) . '_vins';
		$seeded_vins = get_transient( $cache_key );
		if ( is_array( $seeded_vins ) && ! empty( $seeded_vins ) ) {
			$meta_query[] = array(
				'key'     => 'vin_number',
				'value'   => array_values( array_unique( array_map( 'strtoupper', $seeded_vins ) ) ),
				'compare' => 'IN',
			);
		}
	}
	$query->set( 'meta_query', $meta_query );
}
add_action( 'pre_get_posts', 'vch_motors_sync_apply_dom_floor_to_listing_queries', 20 );

function vch_motors_sync_run( $trigger = 'manual' ) {
	$settings      = vch_motors_sync_get_settings();
	$updated_since = (string) get_option( VCH_MOTORS_SYNC_LAST_SYNC_OPTION, '' );
	$state         = array(
		'trigger'          => $trigger,
		'success'          => false,
		'started_at'       => gmdate( 'c' ),
		'completed_at'     => null,
		'pages_processed'  => 0,
		'items_seen'       => 0,
		'items_created'    => 0,
		'items_updated'    => 0,
		'items_skipped_dom'=> 0,
		'items_skipped_invalid_vin'=> 0,
		'items_failed'     => 0,
		'fatal_errors'     => array(),
		'item_errors'      => array(),
		'errors'           => array(),
		'updated_since_in' => $updated_since,
		'updated_since_out'=> $updated_since,
	);

	if ( empty( $settings['export_endpoint'] ) ) {
		return new WP_Error( 'missing_export_endpoint', 'Export endpoint is not configured.' );
	}

	$latest_updated = $updated_since;

	for ( $page = 1; $page <= (int) $settings['max_pages']; $page++ ) {
		$page_result = vch_motors_sync_fetch_export_page( $settings, $page, $updated_since );
		if ( is_wp_error( $page_result ) ) {
			$error_message = $page_result->get_error_message();
			$state['fatal_errors'][] = $error_message;
			$state['errors'][] = $error_message;
			break;
		}

		$items      = $page_result['items'];
		$pagination = $page_result['pagination'];
		$state['pages_processed']++;
		$state['items_seen'] += count( $items );

		foreach ( $items as $item ) {
			$vin = strtoupper( trim( (string) ( $item['vin'] ?? '' ) ) );
			if ( 17 !== strlen( $vin ) ) {
				$state['items_skipped_invalid_vin']++;
				continue;
			}

			$dom_value = vch_motors_sync_to_int( $item['days_on_market'] ?? null );
			if ( null === $dom_value || $dom_value < (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET ) {
				$state['items_skipped_dom']++;
				continue;
			}

			$sync_result = vch_motors_sync_upsert_listing( $item, $settings );
			if ( is_wp_error( $sync_result ) ) {
				$state['items_failed']++;
				if ( count( $state['item_errors'] ) < 20 ) {
					$state['item_errors'][] = $sync_result->get_error_message();
				}
				continue;
			}

			if ( ! empty( $sync_result['created'] ) ) {
				$state['items_created']++;
			} else {
				$state['items_updated']++;
			}

			$item_updated = trim( (string) ( $item['updated_at'] ?? '' ) );
			if ( ! empty( $item_updated ) && ( empty( $latest_updated ) || strcmp( $item_updated, $latest_updated ) > 0 ) ) {
				$latest_updated = $item_updated;
			}
		}

		if ( empty( $pagination['has_next'] ) ) {
			break;
		}
	}

	if ( ! empty( $latest_updated ) ) {
		update_option( VCH_MOTORS_SYNC_LAST_SYNC_OPTION, $latest_updated, false );
		$state['updated_since_out'] = $latest_updated;
	}

	$state['completed_at'] = gmdate( 'c' );
	$state['success']      = empty( $state['fatal_errors'] );

	update_option( VCH_MOTORS_SYNC_STATE_OPTION, $state, false );

	if ( ! empty( $state['fatal_errors'] ) ) {
		return new WP_Error( 'sync_failed', $state['fatal_errors'][0] );
	}

	return $state;
}

function vch_motors_sync_fetch_export_page( $settings, $page, $updated_since, $extra_query = array() ) {
	$query = array(
		'format'             => 'json',
		'page'               => max( 1, (int) $page ),
		'per_page'           => max( 1, (int) $settings['per_page'] ),
		'sort_by'            => 'updated_at',
		'sort_dir'           => 'asc',
		'min_dom'            => (string) (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET,
		'include_unavailable'=> 'true',
		'include_price_stats'=> empty( $settings['include_price_stats'] ) ? 'false' : 'true',
	);

	if ( ! empty( $updated_since ) ) {
		$query['updated_since'] = vch_motors_sync_normalize_updated_since( $updated_since );
	}
	if ( is_array( $extra_query ) && ! empty( $extra_query ) ) {
		foreach ( $extra_query as $key => $value ) {
			if ( ! is_string( $key ) || '' === $key ) {
				continue;
			}
			$query[ $key ] = is_scalar( $value ) ? (string) $value : '';
		}
	}

	$url     = add_query_arg( $query, $settings['export_endpoint'] );
	$headers = array(
		'Accept' => 'application/json',
	);

	if ( ! empty( $settings['auth_bearer_token'] ) ) {
		$headers['Authorization'] = 'Bearer ' . $settings['auth_bearer_token'];
	}

	$response = wp_remote_get(
		$url,
		array(
			'timeout' => 45,
			'headers' => $headers,
		)
	);

	if ( is_wp_error( $response ) ) {
		return $response;
	}

	$code = (int) wp_remote_retrieve_response_code( $response );
	$body = wp_remote_retrieve_body( $response );
	$content_type = (string) wp_remote_retrieve_header( $response, 'content-type' );
	$snippet = vch_motors_sync_error_snippet( $body );
	if ( $code < 200 || $code >= 300 ) {
		return new WP_Error(
			'http_error',
			sprintf(
				'Inventory export request failed (HTTP %1$d, content-type: %2$s). Snippet: %3$s',
				$code,
				$content_type ?: 'n/a',
				$snippet
			)
		);
	}

	$decoded = vch_motors_sync_json_decode_assoc( $body );
	if ( ! is_array( $decoded ) ) {
		return new WP_Error(
			'invalid_payload',
			sprintf(
				'Inventory export payload was not valid JSON (content-type: %1$s). Snippet: %2$s',
				$content_type ?: 'n/a',
				$snippet
			)
		);
	}

	if ( isset( $decoded['status'] ) && ( $decoded['status'] ?? '' ) !== 'ok' ) {
		return new WP_Error(
			'invalid_payload',
			sprintf(
				'Inventory export returned status "%1$s". Snippet: %2$s',
				(string) ( $decoded['status'] ?? '' ),
				$snippet
			)
		);
	}

	// Support both wrapped and unwrapped response shapes.
	$payload = array();
	if ( is_array( $decoded['data'] ?? null ) ) {
		$payload = $decoded['data'];
	} elseif ( isset( $decoded['items'] ) || isset( $decoded['pagination'] ) ) {
		$payload = $decoded;
	} elseif ( ! empty( $decoded['success'] ) && is_array( $decoded['data'] ?? null ) ) {
		$payload = $decoded['data'];
	}

	$items      = is_array( $payload['items'] ?? null ) ? $payload['items'] : array();
	$pagination = is_array( $payload['pagination'] ?? null ) ? $payload['pagination'] : array();
	if ( ! isset( $payload['items'] ) || ! isset( $payload['pagination'] ) ) {
		return new WP_Error(
			'invalid_payload',
			sprintf(
				'Inventory export payload missing items/pagination keys (content-type: %1$s). Snippet: %2$s',
				$content_type ?: 'n/a',
				$snippet
			)
		);
	}

	return array(
		'items'      => $items,
		'pagination' => $pagination,
	);
}

function vch_motors_sync_json_decode_assoc( $body ) {
	$raw = trim( (string) $body );
	if ( '' === $raw ) {
		return null;
	}

	// Remove UTF-8 BOM if upstream includes it.
	if ( 0 === strpos( $raw, "\xEF\xBB\xBF" ) ) {
		$raw = substr( $raw, 3 );
	}

	$decoded = json_decode( $raw, true );
	if ( JSON_ERROR_NONE !== json_last_error() ) {
		return null;
	}

	return $decoded;
}

function vch_motors_sync_error_snippet( $body ) {
	$snippet = trim( wp_strip_all_tags( (string) $body ) );
	if ( '' === $snippet ) {
		return '(empty response)';
	}

	$max_len = (int) VCH_MOTORS_SYNC_MAX_ERROR_SNIPPET;
	if ( strlen( $snippet ) > $max_len ) {
		return substr( $snippet, 0, $max_len ) . '...';
	}

	return $snippet;
}

function vch_motors_sync_upsert_listing( $item, $settings ) {
	$vin = strtoupper( trim( (string) ( $item['vin'] ?? '' ) ) );
	if ( 17 !== strlen( $vin ) ) {
		return new WP_Error( 'invalid_vin', 'Skipping listing with invalid VIN.' );
	}

	$post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	$post_id   = vch_motors_sync_find_listing_post_id( $vin, $post_type );
	$created   = 0 === $post_id;

	$title = trim( (string) ( $item['title'] ?? '' ) );
	if ( empty( $title ) ) {
		$title = trim( sprintf( '%s %s %s %s', (string) ( $item['year'] ?? '' ), (string) ( $item['make'] ?? '' ), (string) ( $item['model'] ?? '' ), (string) ( $item['trim'] ?? '' ) ) );
	}
	if ( empty( $title ) ) {
		$title = $vin;
	}

	$description = vch_motors_sync_resolve_description( $item );

	$post_data = array(
		'post_type'    => $post_type,
		'post_status'  => 'publish',
		'post_title'   => $title,
		'post_content' => $description,
		'post_name'    => sanitize_title( (string) ( $item['slug'] ?? $vin ) ),
	);

	if ( ! $created ) {
		$post_data['ID'] = $post_id;
	}

	$result = wp_insert_post( wp_slash( $post_data ), true );
	if ( is_wp_error( $result ) ) {
		return $result;
	}

	$post_id = (int) $result;

	$price   = vch_motors_sync_to_float( $item['price'] ?? null );
	$mileage = vch_motors_sync_to_int( $item['mileage'] ?? null );
	$state   = trim( (string) ( $item['state'] ?? '' ) );
	$city    = trim( (string) ( $item['city'] ?? '' ) );
	$zip_raw = trim( (string) ( $item['zip'] ?? '' ) );
	$zip_digits = preg_replace( '/[^0-9]/', '', $zip_raw );
	$zip_code = strlen( $zip_digits ) >= 5 ? substr( $zip_digits, 0, 5 ) : '';
	$location = trim( implode( ', ', array_filter( array( $city, $state ) ) ) );
	$history_link = trim( (string) ( $item['source_url'] ?? '' ) );
	if ( empty( $history_link ) ) {
		$history_link = trim( (string) ( $item['vdp_url'] ?? '' ) );
	}

	vch_motors_sync_set_meta( $post_id, 'vin_number', $vin );
	vch_motors_sync_set_meta( $post_id, 'stock_number', substr( $vin, -8 ) );
	vch_motors_sync_set_meta( $post_id, 'price', $price );
	vch_motors_sync_set_meta( $post_id, 'stm_genuine_price', $price );
	vch_motors_sync_set_meta( $post_id, 'mileage', $mileage );
	vch_motors_sync_set_meta( $post_id, 'stm_car_location', $location );
	vch_motors_sync_set_meta( $post_id, 'vch_location_zip', $zip_code );
	vch_motors_sync_set_meta( $post_id, 'vch_location_state', $state );
	vch_motors_sync_set_meta( $post_id, 'vch_location_city', $city );
	vch_motors_sync_set_meta( $post_id, 'history_link', $history_link );
	vch_motors_sync_set_meta( $post_id, 'additional_features', implode( ', ', (array) ( $item['features'] ?? array() ) ) );

	vch_motors_sync_set_meta( $post_id, 'vch_external_id', (string) ( $item['external_id'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_source_type', (string) ( $item['source_type'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_source_priority', vch_motors_sync_to_int( $item['source_priority'] ?? 0 ) );
	vch_motors_sync_set_meta( $post_id, 'vch_source_url', (string) ( $item['source_url'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_vdp_url', (string) ( $item['vdp_url'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_image_display_mode', (string) ( $item['image_display_mode'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_inspection_status', (string) ( $item['inspection_status'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_has_inspection_report', ! empty( $item['has_inspection_report'] ) ? '1' : '0' );
	vch_motors_sync_set_meta( $post_id, 'vch_photos_coming_soon', ! empty( $item['photos_coming_soon'] ) ? '1' : '0' );
	vch_motors_sync_set_meta( $post_id, 'vch_marketcheck_average_retail', vch_motors_sync_to_float( $item['marketcheck_average_retail'] ?? null ) );
	vch_motors_sync_set_meta( $post_id, 'vch_price_delta_marketcheck', vch_motors_sync_to_float( $item['price_delta_marketcheck'] ?? null ) );
	vch_motors_sync_set_meta( $post_id, 'vch_price_delta_marketcheck_pct', vch_motors_sync_to_float( $item['price_delta_marketcheck_pct'] ?? null ) );
	vch_motors_sync_set_meta( $post_id, 'vch_available', ! empty( $item['available'] ) ? '1' : '0' );
	vch_motors_sync_set_meta( $post_id, 'vch_last_seen_active', (string) ( $item['last_seen_active'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_updated_at', (string) ( $item['updated_at'] ?? '' ) );
	vch_motors_sync_set_meta( $post_id, 'vch_days_on_market', vch_motors_sync_to_int( $item['days_on_market'] ?? null ) );
	$remote_image_urls = vch_motors_sync_image_urls_from_item( $item, $settings );
	vch_motors_sync_set_meta( $post_id, 'vch_remote_thumbnail_url', $remote_image_urls[0] ?? '' );
	vch_motors_sync_set_meta( $post_id, 'vch_remote_image_urls', $remote_image_urls );
	vch_motors_sync_set_meta( $post_id, 'vch_remote_image_urls_json', wp_json_encode( $remote_image_urls ) );

	if ( empty( $item['available'] ) ) {
		update_post_meta( $post_id, 'car_mark_as_sold', 'on' );
	} else {
		delete_post_meta( $post_id, 'car_mark_as_sold' );
	}

	vch_motors_sync_apply_listing_attributes( $post_id, $post_type, $item );

	$image_mode = vch_motors_sync_get_image_mode( $settings );
	if ( VCH_MOTORS_SYNC_IMAGE_MODE_ALL === $image_mode ) {
		vch_motors_sync_attach_images( $post_id, $item, $settings );
	} elseif ( VCH_MOTORS_SYNC_IMAGE_MODE_FEATURED === $image_mode ) {
		vch_motors_sync_attach_featured_image( $post_id, $item, $settings );
	}

	clean_post_cache( $post_id );

	return array(
		'post_id'  => $post_id,
		'created'  => $created,
		'vin'      => $vin,
	);
}

function vch_motors_sync_find_listing_post_id( $vin, $post_type ) {
	$posts = get_posts(
		array(
			'post_type'      => $post_type,
			'post_status'    => array( 'publish', 'draft', 'pending', 'private' ),
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_key'       => 'vin_number',
			'meta_value'     => $vin,
		)
	);

	if ( empty( $posts ) ) {
		return 0;
	}

	return (int) $posts[0];
}

function vch_motors_sync_set_meta( $post_id, $key, $value ) {
	if ( null === $value || '' === $value ) {
		delete_post_meta( $post_id, $key );
		return;
	}

	update_post_meta( $post_id, $key, $value );
}

function vch_motors_sync_apply_listing_attributes( $post_id, $post_type, $item ) {
	$filter_options = get_option( 'stm_vehicle_listing_options', array() );
	if ( 'listings' !== $post_type ) {
		$custom_options = get_option( "stm_{$post_type}_options", array() );
		if ( is_array( $custom_options ) && ! empty( $custom_options ) ) {
			$filter_options = $custom_options;
		}
	}

	if ( ! is_array( $filter_options ) ) {
		return;
	}

	foreach ( $filter_options as $filter_option ) {
		if ( empty( $filter_option['slug'] ) ) {
			continue;
		}

		$slug      = sanitize_key( (string) $filter_option['slug'] );
		$is_numeric= ! empty( $filter_option['numeric'] );
		$value     = vch_motors_sync_value_for_attribute_slug( $slug, $item, $is_numeric );
		if ( null === $value || '' === $value ) {
			continue;
		}

		if ( $is_numeric ) {
			vch_motors_sync_set_meta( $post_id, $slug, $value );
			continue;
		}

		if ( taxonomy_exists( $slug ) ) {
			$term = term_exists( (string) $value, $slug );
			if ( ! $term ) {
				$term = wp_insert_term(
					(string) $value,
					$slug,
					array(
						'slug' => sanitize_title( (string) $value ),
					)
				);
			}

				if ( ! is_wp_error( $term ) && ! empty( $term ) ) {
					$term_id = is_array( $term ) ? (int) $term['term_id'] : (int) $term;
					wp_set_object_terms( $post_id, array( $term_id ), $slug, false );
					vch_motors_sync_update_dependency_term_meta( $slug, $term_id, $item );
					$term_obj = get_term( $term_id, $slug );
					if ( $term_obj && ! is_wp_error( $term_obj ) ) {
						vch_motors_sync_set_meta( $post_id, $slug, $term_obj->slug );
					}
				}
		} else {
			vch_motors_sync_set_meta( $post_id, $slug, $value );
		}
	}
}

function vch_motors_sync_update_dependency_term_meta( $slug, $term_id, $item ) {
	$slug = strtolower( (string) $slug );
	$term_id = (int) $term_id;
	if ( $term_id <= 0 ) {
		return;
	}

	$make_slug = sanitize_title( (string) ( $item['make'] ?? '' ) );
	$model_slug = sanitize_title( (string) ( $item['model'] ?? '' ) );

	$is_model_field = ( false !== strpos( $slug, 'model' ) || false !== strpos( $slug, 'serie' ) );
	$is_trim_field = ( false !== strpos( $slug, 'trim' ) );

	if ( $is_model_field && '' !== $make_slug ) {
		// Motors front-end reads dependency maps from term-meta values keyed by parent slug.
		update_term_meta( $term_id, 'make', $make_slug );
	}

	if ( $is_trim_field ) {
		if ( '' !== $make_slug ) {
			update_term_meta( $term_id, 'make', $make_slug );
		}
		if ( '' !== $model_slug ) {
			update_term_meta( $term_id, 'model', $model_slug );
			update_term_meta( $term_id, 'serie', $model_slug );
		}
	}
}

function vch_motors_sync_engine_filter_value( $item ) {
	$cylinders = vch_motors_sync_to_int( $item['cylinders'] ?? null );
	if ( null !== $cylinders ) {
		return $cylinders;
	}

	$engine_text = trim( (string) ( $item['engine_type'] ?? '' ) );
	if ( '' !== $engine_text && preg_match( '/([0-9]+(?:\.[0-9]+)?)/', $engine_text, $matches ) ) {
		return vch_motors_sync_to_float( $matches[1] );
	}

	return null;
}

function vch_motors_sync_fuel_metric_value( $slug, $item ) {
	$slug = strtolower( (string) $slug );
	if ( false !== strpos( $slug, 'consumption' ) ) {
		$city = vch_motors_sync_to_float( $item['city_mpg'] ?? null );
		if ( null !== $city ) {
			return $city;
		}
	}
	if ( false !== strpos( $slug, 'economy' ) ) {
		$highway = vch_motors_sync_to_float( $item['highway_mpg'] ?? null );
		if ( null !== $highway ) {
			return $highway;
		}
	}
	return vch_motors_sync_to_float( $item['mpg_combined'] ?? null );
}

function vch_motors_sync_condition_value( $item ) {
	$inventory_type = strtolower( trim( (string) ( $item['inventory_type'] ?? '' ) ) );
	if ( 'new' === $inventory_type ) {
		return 'New';
	}
	if ( 'used' === $inventory_type ) {
		return 'Used/Certified';
	}
	if ( ! empty( $item['certified'] ) ) {
		return 'Certified';
	}
	return $item['inventory_type'] ?? null;
}

function vch_motors_sync_value_for_attribute_slug( $slug, $item, $is_numeric ) {
	$slug = strtolower( (string) $slug );

	$boolean_map = array(
		'certified'    => ! empty( $item['certified'] ) ? 'Yes' : 'No',
		'single_owner' => ! empty( $item['single_owner'] ) ? 'Yes' : 'No',
		'clean_title'  => ! empty( $item['clean_title'] ) ? 'Yes' : 'No',
	);

		$value_map = array(
			'make'            => $item['make'] ?? null,
			'car-make'        => $item['make'] ?? null,
			'ca-make'         => $item['make'] ?? null,
			'model'           => $item['model'] ?? null,
		'car-model'       => $item['model'] ?? null,
		'ca-model'        => $item['model'] ?? null,
		'vehicle-model'   => $item['model'] ?? null,
		'serie'           => $item['model'] ?? null,
		'trim'            => $item['trim'] ?? null,
		'car-trim'        => $item['trim'] ?? null,
		'ca-trim'         => $item['trim'] ?? null,
		'ca-year'         => $item['year'] ?? null,
		'year'            => $item['year'] ?? null,
		'body'            => $item['body_type'] ?? null,
		'body_type'       => $item['body_type'] ?? null,
		'body-subtype'    => $item['sub_body_type'] ?? null,
		'sub_body_type'   => $item['sub_body_type'] ?? null,
		'drivetrain'      => $item['drivetrain'] ?? null,
		'drive'           => $item['drivetrain'] ?? null,
		'fuel_type'       => $item['fuel_type'] ?? null,
		'fuel'            => $item['fuel_type'] ?? null,
		'fuel-consumption'=> vch_motors_sync_fuel_metric_value( $slug, $item ),
		'fuel-economy'    => vch_motors_sync_fuel_metric_value( $slug, $item ),
		'transmission'    => $item['transmission'] ?? null,
		'engine'          => vch_motors_sync_engine_filter_value( $item ),
		'ev-range'        => $item['ev_range'] ?? null,
		'ev_range'        => $item['ev_range'] ?? null,
		'towing'          => $item['towing_capacity_lbs'] ?? null,
		'towing-capacity' => $item['towing_capacity_lbs'] ?? null,
		'towing_capacity' => $item['towing_capacity_lbs'] ?? null,
		'inventory_type'  => vch_motors_sync_condition_value( $item ),
		'condition'       => vch_motors_sync_condition_value( $item ),
		'mileage'         => $item['mileage'] ?? null,
		'odometer'        => $item['mileage'] ?? null,
		'city'            => $item['city'] ?? null,
		'state'           => $item['state'] ?? null,
		'exterior-color'  => $item['exterior_color'] ?? null,
		'interior-color'  => $item['interior_color'] ?? null,
		'exterior_color'  => $item['exterior_color'] ?? null,
		'interior_color'  => $item['interior_color'] ?? null,
		'days_on_market'  => $item['days_on_market'] ?? null,
		'dom'             => $item['days_on_market'] ?? null,
	);

	if ( isset( $value_map[ $slug ] ) ) {
		return $value_map[ $slug ];
	}

	if ( isset( $boolean_map[ $slug ] ) ) {
		return $boolean_map[ $slug ];
	}

	if ( false !== strpos( $slug, 'make' ) ) {
		return $item['make'] ?? null;
	}
	if ( false !== strpos( $slug, 'model' ) || false !== strpos( $slug, 'serie' ) ) {
		return $item['model'] ?? null;
	}
	if ( false !== strpos( $slug, 'trim' ) ) {
		return $item['trim'] ?? null;
	}
	if ( false !== strpos( $slug, 'year' ) ) {
		return $item['year'] ?? null;
	}
	if ( false !== strpos( $slug, 'body' ) ) {
		return $item['body_type'] ?? null;
	}
	if ( ( false !== strpos( $slug, 'ev' ) && false !== strpos( $slug, 'range' ) ) || false !== strpos( $slug, 'electric_range' ) ) {
		return vch_motors_sync_to_int( $item['ev_range'] ?? null );
	}
	if ( false !== strpos( $slug, 'tow' ) ) {
		return vch_motors_sync_to_int( $item['towing_capacity_lbs'] ?? null );
	}
	if ( false !== strpos( $slug, 'engine' ) ) {
		return vch_motors_sync_engine_filter_value( $item );
	}
	if ( false !== strpos( $slug, 'consumption' ) || false !== strpos( $slug, 'economy' ) || false !== strpos( $slug, 'mpg' ) ) {
		return vch_motors_sync_fuel_metric_value( $slug, $item );
	}
	if ( false !== strpos( $slug, 'fuel' ) ) {
		return $item['fuel_type'] ?? null;
	}
	if ( false !== strpos( $slug, 'trans' ) ) {
		return $item['transmission'] ?? null;
	}
	if ( false !== strpos( $slug, 'drive' ) ) {
		return $item['drivetrain'] ?? null;
	}
	if ( false !== strpos( $slug, 'mile' ) || false !== strpos( $slug, 'odometer' ) ) {
		return $item['mileage'] ?? null;
	}
	if ( false !== strpos( $slug, 'city' ) ) {
		return $item['city'] ?? null;
	}
	if ( false !== strpos( $slug, 'state' ) ) {
		return $item['state'] ?? null;
	}
	if ( false !== strpos( $slug, 'interior' ) && false !== strpos( $slug, 'color' ) ) {
		return $item['interior_color'] ?? null;
	}
	if ( false !== strpos( $slug, 'color' ) ) {
		return $item['exterior_color'] ?? null;
	}
	if ( false !== strpos( $slug, 'cert' ) ) {
		return ! empty( $item['certified'] ) ? 'Yes' : 'No';
	}
	if ( false !== strpos( $slug, 'owner' ) ) {
		return ! empty( $item['single_owner'] ) ? 'Yes' : 'No';
	}
	if ( false !== strpos( $slug, 'title' ) && false !== strpos( $slug, 'clean' ) ) {
		return ! empty( $item['clean_title'] ) ? 'Yes' : 'No';
	}
	if ( false !== strpos( $slug, 'inventory' ) || false !== strpos( $slug, 'condition' ) ) {
		return vch_motors_sync_condition_value( $item );
	}
	if ( false !== strpos( $slug, 'dom' ) || false !== strpos( $slug, 'days' ) ) {
		return $item['days_on_market'] ?? null;
	}

	if ( $is_numeric ) {
		return null;
	}

	return null;
}

function vch_motors_sync_resolve_description( $item ) {
	$description = trim( (string) ( $item['description'] ?? '' ) );
	if ( ! empty( $description ) && false === stripos( $description, 'lorem ipsum' ) ) {
		return $description;
	}

	$title = trim(
		sprintf(
			'%s %s %s %s',
			(string) ( $item['year'] ?? '' ),
			(string) ( $item['make'] ?? '' ),
			(string) ( $item['model'] ?? '' ),
			(string) ( $item['trim'] ?? '' )
		)
	);
	if ( empty( $title ) ) {
		$title = trim( (string) ( $item['vin'] ?? 'Vehicle listing' ) );
	}

	$parts = array();
	$mileage = vch_motors_sync_to_int( $item['mileage'] ?? null );
	if ( null !== $mileage ) {
		$parts[] = number_format_i18n( $mileage ) . ' miles';
	}
	foreach ( array( 'fuel_type', 'transmission', 'drivetrain', 'exterior_color', 'interior_color' ) as $key ) {
		$value = trim( (string) ( $item[ $key ] ?? '' ) );
		if ( ! empty( $value ) ) {
			$parts[] = $value;
		}
	}

	$city = trim( (string) ( $item['city'] ?? '' ) );
	$state = trim( (string) ( $item['state'] ?? '' ) );
	$location = trim( implode( ', ', array_filter( array( $city, $state ) ) ) );
	$dom = vch_motors_sync_to_int( $item['days_on_market'] ?? null );
	$feature_list = array_slice( array_filter( array_map( 'trim', (array) ( $item['features'] ?? array() ) ) ), 0, 6 );

	$summary = $title . '.';
	if ( ! empty( $parts ) ) {
		$summary .= ' Specs: ' . implode( ', ', $parts ) . '.';
	}
	if ( ! empty( $location ) ) {
		$summary .= ' Located in ' . $location . '.';
	}
	if ( null !== $dom ) {
		$summary .= ' Days on market: ' . (int) $dom . '.';
	}
	if ( ! empty( $feature_list ) ) {
		$summary .= ' Highlights: ' . implode( ', ', $feature_list ) . '.';
	}

	return $summary;
}

function vch_motors_sync_attach_images( $post_id, $item, $settings ) {
	$image_urls = vch_motors_sync_image_urls_from_item( $item, $settings );
	if ( empty( $image_urls ) ) {
		return;
	}

	$fingerprint = sha1( implode( '|', $image_urls ) );
	$existing    = (string) get_post_meta( $post_id, '_vch_image_fingerprint', true );
	if ( ! empty( $existing ) && hash_equals( $existing, $fingerprint ) ) {
		return;
	}

	require_once ABSPATH . 'wp-admin/includes/file.php';
	require_once ABSPATH . 'wp-admin/includes/media.php';
	require_once ABSPATH . 'wp-admin/includes/image.php';

	$attachment_ids = array();
	foreach ( $image_urls as $url ) {
		$attachment_id = vch_motors_sync_find_attachment_by_source_url( $url );
		if ( ! $attachment_id ) {
			$attachment_id = vch_motors_sync_sideload_image( $url, $post_id, $settings );
		}
		if ( $attachment_id ) {
			$attachment_ids[] = $attachment_id;
		}
	}

	if ( empty( $attachment_ids ) ) {
		return;
	}

	set_post_thumbnail( $post_id, $attachment_ids[0] );
	update_post_meta( $post_id, 'gallery', array_slice( $attachment_ids, 1 ) );
	update_post_meta( $post_id, '_vch_image_fingerprint', $fingerprint );
	update_post_meta( $post_id, '_vch_images_synced_at', gmdate( 'c' ) );
}

function vch_motors_sync_attach_featured_image( $post_id, $item, $settings ) {
	$image_urls = vch_motors_sync_image_urls_from_item( $item, $settings );
	if ( empty( $image_urls ) ) {
		return;
	}

	require_once ABSPATH . 'wp-admin/includes/file.php';
	require_once ABSPATH . 'wp-admin/includes/media.php';
	require_once ABSPATH . 'wp-admin/includes/image.php';

	$url           = $image_urls[0];
	$attachment_id = vch_motors_sync_find_attachment_by_source_url( $url );
	if ( ! $attachment_id ) {
		$attachment_id = vch_motors_sync_sideload_image( $url, $post_id, $settings );
	}
	if ( ! $attachment_id ) {
		return;
	}

	set_post_thumbnail( $post_id, $attachment_id );
}

function vch_motors_sync_image_urls_from_item( $item, $settings ) {
	$urls = array();

	if ( ! empty( $item['images'] ) && is_array( $item['images'] ) ) {
		$urls = $item['images'];
	} elseif ( ! empty( $item['image_urls'] ) && is_string( $item['image_urls'] ) ) {
		$delimiter = false !== strpos( $item['image_urls'], '|' ) ? '|' : ',';
		$urls      = explode( $delimiter, $item['image_urls'] );
	}

	if ( empty( $urls ) && ! empty( $item['thumbnail'] ) ) {
		$urls = array( $item['thumbnail'] );
	}

	$normalized = array();
	foreach ( $urls as $url ) {
		$text = trim( (string) $url );
		if ( empty( $text ) ) {
			continue;
		}
		$normalized[] = esc_url_raw( $text );
	}

	$deduped = array_values( array_unique( array_filter( $normalized ) ) );
	$limit   = max( 0, absint( $settings['max_images_per_listing'] ?? VCH_MOTORS_SYNC_DEFAULT_MAX_IMAGES_PER_LISTING ) );
	if ( $limit > 0 ) {
		return array_slice( $deduped, 0, $limit );
	}

	return $deduped;
}

function vch_motors_sync_find_attachment_by_source_url( $url ) {
	$posts = get_posts(
		array(
			'post_type'      => 'attachment',
			'post_status'    => 'inherit',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_key'       => '_vch_source_image_url',
			'meta_value'     => $url,
		)
	);

	if ( empty( $posts ) ) {
		return 0;
	}

	return (int) $posts[0];
}

function vch_motors_sync_sideload_image( $url, $post_id, $settings ) {
	$timeout        = max( 5, absint( $settings['image_download_timeout_sec'] ?? VCH_MOTORS_SYNC_DEFAULT_IMAGE_DOWNLOAD_TIMEOUT_SEC ) );
	$temporary_file = download_url( $url, $timeout );
	if ( is_wp_error( $temporary_file ) ) {
		return 0;
	}

	$path = wp_parse_url( $url, PHP_URL_PATH );
	$name = basename( $path ? $path : '' );
	if ( empty( $name ) ) {
		$name = 'vehicle-image.jpg';
	}

	$file_array = array(
		'name'     => sanitize_file_name( $name ),
		'tmp_name' => $temporary_file,
	);

	$attachment_id = media_handle_sideload( $file_array, $post_id );
	if ( is_wp_error( $attachment_id ) ) {
		@unlink( $temporary_file );
		return 0;
	}

	update_post_meta( $attachment_id, '_vch_source_image_url', $url );

	return (int) $attachment_id;
}

function vch_motors_sync_html_has_placeholder_thumbnail( $html ) {
	$text = strtolower( trim( wp_strip_all_tags( (string) $html ) ) );
	$raw  = strtolower( (string) $html );
	if ( '' === $raw ) {
		return false;
	}

	$patterns = array(
		'placeholder',
		'no-image',
		'no_image',
		'coming-soon',
		'coming_soon',
		'stm-placeholder',
		'stm_no_photo',
		'cars-placeholder',
	);
	foreach ( $patterns as $pattern ) {
		if ( false !== strpos( $raw, $pattern ) || false !== strpos( $text, $pattern ) ) {
			return true;
		}
	}

	return false;
}

function vch_motors_sync_external_thumbnail_html( $html, $post_id, $post_thumbnail_id, $size, $attr ) {
	if ( ! empty( $post_thumbnail_id ) && ! vch_motors_sync_html_has_placeholder_thumbnail( $html ) ) {
		return $html;
	}

	$post = get_post( $post_id );
	if ( ! ( $post instanceof WP_Post ) ) {
		return $html;
	}

	$settings         = vch_motors_sync_get_settings();
	$target_post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	if ( empty( $target_post_type ) ) {
		$target_post_type = 'listings';
	}
	if ( $post->post_type !== $target_post_type ) {
		return $html;
	}

	$url = trim( (string) get_post_meta( $post_id, 'vch_remote_thumbnail_url', true ) );
	if ( '' === $url ) {
		return $html;
	}

	$classes = array( 'vch-remote-thumbnail', 'attachment-post-thumbnail', 'size-post-thumbnail', 'wp-post-image' );
	if ( is_array( $attr ) && ! empty( $attr['class'] ) ) {
		$classes[] = (string) $attr['class'];
	}
	$class_attr = trim( implode( ' ', array_filter( $classes ) ) );

	return sprintf(
		'<img src="%1$s" alt="%2$s" class="%3$s" loading="lazy" decoding="async" />',
		esc_url( $url ),
		esc_attr( get_the_title( $post_id ) ),
		esc_attr( $class_attr )
	);
}
add_filter( 'post_thumbnail_html', 'vch_motors_sync_external_thumbnail_html', 10, 5 );

function vch_motors_sync_get_remote_images_for_post( $post_id ) {
	$raw = get_post_meta( $post_id, 'vch_remote_image_urls', true );
	$list = array();
	if ( is_array( $raw ) ) {
		$list = $raw;
	} else {
		$json = get_post_meta( $post_id, 'vch_remote_image_urls_json', true );
		if ( is_string( $json ) && '' !== trim( $json ) ) {
			$decoded = json_decode( $json, true );
			if ( is_array( $decoded ) ) {
				$list = $decoded;
			}
		}
	}

	$normalized = array();
	foreach ( $list as $url ) {
		$text = trim( (string) $url );
		if ( '' === $text ) {
			continue;
		}
		$normalized[] = esc_url_raw( $text );
	}

	$normalized = array_values( array_unique( array_filter( $normalized ) ) );
	if ( ! empty( $normalized ) ) {
		return $normalized;
	}

	$thumbnail = trim( (string) get_post_meta( $post_id, 'vch_remote_thumbnail_url', true ) );
	return '' === $thumbnail ? array() : array( esc_url_raw( $thumbnail ) );
}

function vch_motors_sync_enqueue_remote_gallery_assets() {
	if ( is_admin() ) {
		return;
	}

	$settings         = vch_motors_sync_get_settings();
	$target_post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	if ( empty( $target_post_type ) ) {
		$target_post_type = 'listings';
	}
	if ( ! is_singular( $target_post_type ) ) {
		return;
	}

	if ( VCH_MOTORS_SYNC_IMAGE_MODE_EXTERNAL !== vch_motors_sync_get_image_mode( $settings ) ) {
		return;
	}

	$post_id = get_queried_object_id();
	if ( empty( $post_id ) ) {
		return;
	}

	$images = vch_motors_sync_get_remote_images_for_post( (int) $post_id );
	if ( empty( $images ) ) {
		return;
	}

	$config = array(
		'postId' => (int) $post_id,
		'images' => array_values( $images ),
	);

	$gallery_css = <<<'CSS'
.vch-compact-vdp-hero,
.stm-single-car-title-box.vch-compact-vdp-hero,
.stm-directory-title-box.vch-compact-vdp-hero,
.page-title.vch-compact-vdp-hero,
.single-listing-page-title.vch-compact-vdp-hero {
	min-height: 0 !important;
	padding: 28px 0 18px !important;
	margin-bottom: 0 !important;
	background: #5f6875 !important;
}
.vch-compact-vdp-hero::before,
.vch-compact-vdp-hero::after {
	opacity: 0 !important;
}
.vch-compact-vdp-hero h1,
.vch-compact-vdp-hero h2,
.vch-compact-vdp-hero .title {
	margin: 0 !important;
	line-height: 1.05 !important;
}
.stm_breadcrumbs_unit,
.stm-single-car-page .stm-breadcrumbs-wrap,
.stm-single-car-page .breadcrumbs,
.stm-single-car-page .stm_breadcrumbs {
	padding-top: 12px !important;
	padding-bottom: 12px !important;
	margin-bottom: 12px !important;
}
.stm-single-car-page .stm-car-carousels,
.stm-single-car-page .stm-single-car-gallery,
.stm-single-car-page .stm-listing-single-car__gallery,
.stm-single-car-page .single-listing-car-gallery,
.stm-single-car-page .car-listing-gallery {
	margin-top: 0 !important;
}
.vch-remote-gallery {
	width: min(100%, 1040px);
	margin: 0 auto 20px;
}
.vch-remote-gallery-main {
	display: flex;
	align-items: center;
	justify-content: center;
	aspect-ratio: 16 / 10;
	max-height: min(62vh, 520px);
	margin-bottom: 10px;
	padding: 10px;
	overflow: hidden;
	background: #f4f6f8;
	border-radius: 8px;
}
.vch-remote-gallery-main img {
	display: block;
	max-width: 100%;
	max-height: 100%;
	width: auto;
	height: auto;
	object-fit: contain;
	border-radius: 4px;
}
.vch-remote-gallery-thumbs {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
	gap: 8px;
}
.vch-remote-gallery-thumb {
	background: none;
	border: 0;
	padding: 0;
	cursor: pointer;
}
.vch-remote-gallery-thumb img {
	display: block;
	width: 100%;
	height: 68px;
	object-fit: cover;
	border-radius: 4px;
	opacity: .85;
	transition: opacity .15s ease;
}
.vch-remote-gallery-thumb.is-active img,
.vch-remote-gallery-thumb:hover img {
	opacity: 1;
}
.vch-remote-gallery-thumb:focus-visible {
	outline: 2px solid #4061b6;
	outline-offset: 2px;
}
@media (max-width: 767px) {
	.vch-compact-vdp-hero,
	.stm-single-car-title-box.vch-compact-vdp-hero,
	.stm-directory-title-box.vch-compact-vdp-hero,
	.page-title.vch-compact-vdp-hero,
	.single-listing-page-title.vch-compact-vdp-hero {
		padding: 22px 0 14px !important;
	}
	.vch-remote-gallery-main {
		aspect-ratio: 4 / 3;
		max-height: 46vh;
	}
}
CSS;
	wp_register_style( 'vch-motors-remote-gallery', false, array(), VCH_MOTORS_SYNC_VERSION );
	wp_enqueue_style( 'vch-motors-remote-gallery' );
	wp_add_inline_style( 'vch-motors-remote-gallery', $gallery_css );

	wp_register_script( 'vch-motors-remote-gallery', '', array(), VCH_MOTORS_SYNC_VERSION, true );
	wp_enqueue_script( 'vch-motors-remote-gallery' );
	wp_add_inline_script(
		'vch-motors-remote-gallery',
		'window.VCHRemoteGalleryConfig=' . wp_json_encode( $config ) . ';',
		'before'
	);
	$gallery_script = <<<'JS'
(function(){
	var cfg = window.VCHRemoteGalleryConfig || {};
	var images = Array.isArray(cfg.images) ? cfg.images.filter(Boolean) : [];
	if (!images.length) {
		return;
	}
	var selectors = [
		'.stm-car-carousels',
		'.stm-single-car-page .stm-car-carousels',
		'.stm-single-car-gallery',
		'.stm-listing-single-car__gallery',
		'.single-listing-car-gallery',
		'.car-listing-gallery'
	];
	var titleSelectors = [
		'.stm-single-car-title-box',
		'.stm-directory-title-box',
		'.single-listing-page-title',
		'.page-title',
		'.entry-header'
	];
	var target = null;
	for (var i = 0; i < selectors.length; i += 1) {
		var node = document.querySelector(selectors[i]);
		if (node) {
			target = node;
			break;
		}
	}
	function esc(value) {
		return String(value).replace(/[&<>\"']/g, function(ch) {
			return ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'})[ch] || ch;
		});
	}
	function markup(urls) {
		var main = urls[0];
		var thumbs = '';
		for (var j = 0; j < urls.length; j += 1) {
			thumbs += '<button type="button" class="vch-remote-gallery-thumb' + (j === 0 ? ' is-active' : '') + '" data-vch-gallery-index="' + j + '" aria-label="Show image ' + (j + 1) + '"><img src="' + esc(urls[j]) + '" alt="Vehicle image ' + (j + 1) + '" loading="lazy" decoding="async"></button>';
		}
		return '<div class="vch-remote-gallery" data-vch-remote-gallery="1"><div class="vch-remote-gallery-main"><img src="' + esc(main) + '" alt="Vehicle image" loading="eager" decoding="async"></div><div class="vch-remote-gallery-thumbs">' + thumbs + '</div></div>';
	}
	function bind(root, urls) {
		root.addEventListener('click', function(event) {
			var btn = event.target && event.target.closest ? event.target.closest('[data-vch-gallery-index]') : null;
			if (!btn) {
				return;
			}
			var idx = Number(btn.getAttribute('data-vch-gallery-index') || '0');
			if (Number.isNaN(idx) || idx < 0 || idx >= urls.length) {
				return;
			}
			var mainImg = root.querySelector('.vch-remote-gallery-main img');
			if (mainImg) {
				mainImg.src = urls[idx];
			}
			var all = root.querySelectorAll('.vch-remote-gallery-thumb');
			for (var k = 0; k < all.length; k += 1) {
				all[k].classList.toggle('is-active', all[k] === btn);
			}
		});
	}
	function compactHero() {
		for (var i = 0; i < titleSelectors.length; i += 1) {
			var hero = document.querySelector(titleSelectors[i]);
			if (!hero) {
				continue;
			}
			var height = hero.getBoundingClientRect ? hero.getBoundingClientRect().height : 0;
			if (height < 160 && !hero.querySelector('h1, h2, .title')) {
				continue;
			}
			hero.classList.add('vch-compact-vdp-hero');
		}
	}
	if (target) {
		target.innerHTML = markup(images);
		bind(target, images);
		compactHero();
		return;
	}
	var fallback = document.querySelector('.stm-single-car-page .container') || document.querySelector('.stm-single-car-page') || document.querySelector('.site-content') || document.querySelector('main') || document.body;
	if (!fallback) {
		return;
	}
	var mount = document.createElement('div');
	mount.innerHTML = markup(images);
	var el = mount.firstElementChild;
	if (!el) {
		return;
	}
	var breadcrumbs = document.querySelector('.stm_breadcrumbs_unit') || document.querySelector('.stm-single-car-page .breadcrumbs');
	if (breadcrumbs && breadcrumbs.parentNode) {
		breadcrumbs.parentNode.insertBefore(el, breadcrumbs.nextSibling);
	} else {
		fallback.insertBefore(el, fallback.firstChild);
	}
	bind(el, images);
	compactHero();
})();
JS;
	wp_add_inline_script( 'vch-motors-remote-gallery', $gallery_script );
}
add_action( 'wp_enqueue_scripts', 'vch_motors_sync_enqueue_remote_gallery_assets', 100 );

function vch_motors_sync_print_archive_thumbnail_fallback_script() {
	if ( is_admin() ) {
		return;
	}
	if ( is_singular() ) {
		return;
	}

	$settings         = vch_motors_sync_get_settings();
	$target_post_type = sanitize_key( (string) ( $settings['post_type'] ?? 'listings' ) );
	if ( '' === $target_post_type ) {
		$target_post_type = 'listings';
	}

	global $wp_query;
	if ( ! ( $wp_query instanceof WP_Query ) ) {
		return;
	}

	$posts = is_array( $wp_query->posts ?? null ) ? $wp_query->posts : array();
	if ( empty( $posts ) ) {
		return;
	}

	$map = array();
	foreach ( $posts as $post_obj ) {
		$post_id = (int) ( $post_obj->ID ?? 0 );
		if ( $post_id <= 0 ) {
			continue;
		}
		$post_type = get_post_type( $post_id );
		if ( $target_post_type !== $post_type ) {
			continue;
		}
		$url = trim( (string) get_post_meta( $post_id, 'vch_remote_thumbnail_url', true ) );
		if ( '' === $url ) {
			continue;
		}
		$permalink = get_permalink( $post_id );
		if ( empty( $permalink ) ) {
			continue;
		}
		$map[] = array(
			'postId'    => $post_id,
			'permalink' => esc_url_raw( $permalink ),
			'thumbnail' => esc_url_raw( $url ),
			'title'     => get_the_title( $post_id ),
		);
	}

	if ( empty( $map ) ) {
		return;
	}

	$json = wp_json_encode( $map );
	if ( empty( $json ) ) {
		return;
	}
	?>
	<script id="vch-archive-thumb-fallback">
	(function(){
		var raw = <?php echo $json; ?>;
		if (!Array.isArray(raw) || !raw.length) { return; }
		function norm(input) {
			try {
				var u = new URL(String(input), window.location.origin);
				return u.pathname.replace(/\/+$/, '');
			} catch (e) {
				return String(input || '').replace(/\/+$/, '');
			}
		}
		function applyToImage(img, thumb, title) {
			if (!img) { return false; }
			img.setAttribute('src', thumb);
			img.setAttribute('data-src', thumb);
			img.setAttribute('data-lazy-src', thumb);
			img.setAttribute('data-original', thumb);
			img.setAttribute('alt', title || 'Vehicle image');
			img.removeAttribute('srcset');
			img.removeAttribute('data-srcset');
			return true;
		}
		function injectIntoMediaBox(box, thumb, title) {
			if (!box) { return false; }
			box.style.backgroundImage = 'url(\"' + thumb.replace(/"/g, '\\"') + '\")';
			box.style.backgroundSize = 'cover';
			box.style.backgroundPosition = 'center';
			box.style.backgroundRepeat = 'no-repeat';
			var img = box.querySelector('img');
			if (img) { return applyToImage(img, thumb, title); }
			var inserted = document.createElement('img');
			inserted.className = 'vch-archive-thumb wp-post-image';
			inserted.loading = 'lazy';
			inserted.decoding = 'async';
			inserted.style.width = '100%';
			inserted.style.height = '100%';
			inserted.style.objectFit = 'cover';
			inserted.style.display = 'block';
			applyToImage(inserted, thumb, title);
			box.appendChild(inserted);
			return true;
		}
		function findCard(entry) {
			if (entry.postId) {
				var byId = document.getElementById('post-' + entry.postId);
				if (byId) { return byId; }
			}
			var permalink = norm(entry.permalink || '');
			if (!permalink) { return null; }
			var links = document.querySelectorAll('a[href]');
			for (var i = 0; i < links.length; i += 1) {
				if (norm(links[i].getAttribute('href') || '') !== permalink) { continue; }
				var card = links[i].closest('article, .listing, .car-listing, .stm-car-listing, .stm_inventory_item, .stm-directory-grid-loop, .listing-item, .stm-cab-grid-loop, .stm-loop-single-listing');
				if (card) { return card; }
			}
			return null;
		}
		function patchEntry(entry) {
			var thumb = entry.thumbnail || '';
			if (!thumb) { return; }
			var card = findCard(entry);
			if (!card) { return; }
			var img = card.querySelector('img.wp-post-image, img[data-src], img[data-lazy-src], img');
			if (img) {
				applyToImage(img, thumb, entry.title || '');
				return;
			}
			var mediaBox = card.querySelector('.image, .image-inner, .stm-image, .stm-car-medias, .stm-listing-photo, .car-listing-media, .listing-car-item-meta .image, .stm-directory-grid-loop__image');
			injectIntoMediaBox(mediaBox, thumb, entry.title || '');
		}
		function patch() {
			for (var i = 0; i < raw.length; i += 1) {
				patchEntry(raw[i]);
			}
		}
		if (document.readyState === 'loading') {
			document.addEventListener('DOMContentLoaded', patch);
		} else {
			patch();
		}
		if (window.MutationObserver && document.body) {
			var scheduled = false;
			var observer = new MutationObserver(function() {
				if (scheduled) { return; }
				scheduled = true;
				window.requestAnimationFrame(function() {
					scheduled = false;
					patch();
				});
			});
			observer.observe(document.body, {childList: true, subtree: true});
		}
		setTimeout(patch, 400);
		setTimeout(patch, 1200);
		setTimeout(patch, 2500);
	})();
	</script>
	<?php
}
add_action( 'wp_footer', 'vch_motors_sync_print_archive_thumbnail_fallback_script', 110 );

function vch_motors_sync_to_float( $value ) {
	if ( null === $value || '' === $value ) {
		return null;
	}
	if ( ! is_numeric( $value ) ) {
		return null;
	}
	return round( (float) $value, 2 );
}

function vch_motors_sync_normalize_updated_since( $value ) {
	$text = trim( (string) $value );
	if ( '' === $text ) {
		return '';
	}

	$timestamp = strtotime( $text );
	if ( false === $timestamp ) {
		return $text;
	}

	// Use Z suffix so query parsing does not reinterpret '+' as whitespace.
	return gmdate( 'Y-m-d\\TH:i:s\\Z', $timestamp );
}

function vch_motors_sync_to_int( $value ) {
	if ( null === $value || '' === $value ) {
		return null;
	}
	if ( ! is_numeric( $value ) ) {
		return null;
	}
	return (int) round( (float) $value );
}

function vch_motors_sync_inventory_widget_shortcode( $atts ) {
	$atts = shortcode_atts(
		array(
			'src'        => 'https://app.virtualcarhub.com/vinventory',
			'min_height' => '2400px',
			'title'      => 'VirtualCarHub Inventory',
			'class'      => '',
			'loading'    => 'lazy',
		),
		$atts,
		'vch_inventory_widget'
	);

	$src        = esc_url( trim( (string) $atts['src'] ) );
	$min_height = preg_replace( '/[^0-9a-z%.\-]/i', '', (string) $atts['min_height'] );
	$title      = sanitize_text_field( (string) $atts['title'] );
	$class      = sanitize_html_class( (string) $atts['class'] );
	$loading    = strtolower( trim( (string) $atts['loading'] ) );

	if ( '' === $src ) {
		return '';
	}

	if ( '' === $min_height ) {
		$min_height = '2400px';
	}

	if ( 'eager' !== $loading ) {
		$loading = 'lazy';
	}

	$wrapper_class = 'vch-inventory-widget-embed';
	if ( '' !== $class ) {
		$wrapper_class .= ' ' . $class;
	}

	ob_start();
	?>
	<div class="<?php echo esc_attr( $wrapper_class ); ?>">
		<iframe
			src="<?php echo esc_url( $src ); ?>"
			title="<?php echo esc_attr( $title ); ?>"
			loading="<?php echo esc_attr( $loading ); ?>"
			referrerpolicy="strict-origin-when-cross-origin"
			style="width:100%;min-height:<?php echo esc_attr( $min_height ); ?>;border:0;display:block;background:transparent;"
		></iframe>
	</div>
	<?php
	return (string) ob_get_clean();
}
add_shortcode( 'vch_inventory_widget', 'vch_motors_sync_inventory_widget_shortcode' );
