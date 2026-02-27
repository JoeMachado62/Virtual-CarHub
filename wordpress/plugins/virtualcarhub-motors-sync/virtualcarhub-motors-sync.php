<?php
/**
 * Plugin Name: VirtualCarHub Motors Sync
 * Description: Sync VirtualCarHub inventory API listings into Motors listing posts with image and attribute mapping.
 * Version: 0.1.0
 * Author: VirtualCarHub
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'VCH_MOTORS_SYNC_VERSION', '0.1.0' );
define( 'VCH_MOTORS_SYNC_SETTINGS_OPTION', 'vch_motors_sync_settings' );
define( 'VCH_MOTORS_SYNC_STATE_OPTION', 'vch_motors_sync_state' );
define( 'VCH_MOTORS_SYNC_LAST_SYNC_OPTION', 'vch_motors_sync_last_synced_at' );
define( 'VCH_MOTORS_SYNC_LAST_TEST_OPTION', 'vch_motors_sync_last_test_result' );
define( 'VCH_MOTORS_SYNC_CRON_HOOK', 'vch_motors_sync_run_event' );
define( 'VCH_MOTORS_SYNC_NONCE_ACTION', 'vch_motors_sync_now' );
define( 'VCH_MOTORS_SYNC_NONCE_NAME', 'vch_motors_sync_nonce' );
define( 'VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET', 45 );

function vch_motors_sync_default_settings() {
	return array(
		'export_endpoint'     => 'https://virtualcarhub.com/api/vch/inventory/wordpress/export',
		'auth_bearer_token'   => '',
		'post_type'           => 'listings',
		'per_page'            => 100,
		'max_pages'           => 10,
		'include_price_stats' => 0,
		'download_images'     => 1,
		'cron_interval'       => 'hourly',
	);
}

function vch_motors_sync_get_settings() {
	$saved    = get_option( VCH_MOTORS_SYNC_SETTINGS_OPTION, array() );
	$defaults = vch_motors_sync_default_settings();
	if ( ! is_array( $saved ) ) {
		$saved = array();
	}

	return wp_parse_args( $saved, $defaults );
}

function vch_motors_sync_sanitize_settings( $input ) {
	$defaults = vch_motors_sync_default_settings();
	if ( ! is_array( $input ) ) {
		$input = array();
	}

	$settings                         = $defaults;
	$settings['export_endpoint']      = esc_url_raw( trim( (string) ( $input['export_endpoint'] ?? $defaults['export_endpoint'] ) ) );
	$settings['auth_bearer_token']    = trim( (string) ( $input['auth_bearer_token'] ?? '' ) );
	$settings['post_type']            = sanitize_key( (string) ( $input['post_type'] ?? $defaults['post_type'] ) );
	$settings['per_page']             = min( 500, max( 1, absint( $input['per_page'] ?? $defaults['per_page'] ) ) );
	$settings['max_pages']            = min( 100, max( 1, absint( $input['max_pages'] ?? $defaults['max_pages'] ) ) );
	$settings['include_price_stats']  = empty( $input['include_price_stats'] ) ? 0 : 1;
	$settings['download_images']      = empty( $input['download_images'] ) ? 0 : 1;
	$allowed_intervals                = array( 'fifteen_minutes', 'hourly', 'twicedaily', 'daily' );
	$settings['cron_interval']        = in_array( $input['cron_interval'] ?? '', $allowed_intervals, true )
		? $input['cron_interval']
		: $defaults['cron_interval'];

	if ( empty( $settings['export_endpoint'] ) ) {
		$settings['export_endpoint'] = $defaults['export_endpoint'];
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
					<th scope="row"><label for="vch_auth_bearer"><?php esc_html_e( 'Bearer Token (Optional)', 'virtualcarhub-motors-sync' ); ?></label></th>
					<td><input name="<?php echo esc_attr( VCH_MOTORS_SYNC_SETTINGS_OPTION ); ?>[auth_bearer_token]" id="vch_auth_bearer" type="password" class="regular-text code" value="<?php echo esc_attr( $settings['auth_bearer_token'] ); ?>"></td>
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

function vch_motors_sync_admin_redirect( $status, $action ) {
	wp_safe_redirect(
		add_query_arg(
			array(
				'page'            => 'vch-motors-sync',
				'vch_sync_status' => $status,
				'vch_sync_action' => $action,
			),
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

function vch_motors_sync_run_cron() {
	vch_motors_sync_run( 'cron' );
}
add_action( VCH_MOTORS_SYNC_CRON_HOOK, 'vch_motors_sync_run_cron' );

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

	if ( ! $matches ) {
		return;
	}

	$meta_query   = $query->get( 'meta_query' );
	$meta_query   = is_array( $meta_query ) ? $meta_query : array();
	$meta_query[] = array(
		'key'     => 'vch_days_on_market',
		'value'   => (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET,
		'compare' => '>=',
		'type'    => 'NUMERIC',
	);
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
		'items_failed'     => 0,
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
			$state['errors'][] = $page_result->get_error_message();
			break;
		}

		$items      = $page_result['items'];
		$pagination = $page_result['pagination'];
		$state['pages_processed']++;
		$state['items_seen'] += count( $items );

		foreach ( $items as $item ) {
			$dom_value = vch_motors_sync_to_int( $item['days_on_market'] ?? null );
			if ( null === $dom_value || $dom_value < (int) VCH_MOTORS_SYNC_MIN_DAYS_ON_MARKET ) {
				$state['items_skipped_dom']++;
				continue;
			}

			$sync_result = vch_motors_sync_upsert_listing( $item, $settings );
			if ( is_wp_error( $sync_result ) ) {
				$state['items_failed']++;
				$state['errors'][] = $sync_result->get_error_message();
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

	if ( empty( $state['errors'] ) && ! empty( $latest_updated ) ) {
		update_option( VCH_MOTORS_SYNC_LAST_SYNC_OPTION, $latest_updated, false );
		$state['updated_since_out'] = $latest_updated;
	}

	$state['completed_at'] = gmdate( 'c' );
	$state['success']      = empty( $state['errors'] );

	update_option( VCH_MOTORS_SYNC_STATE_OPTION, $state, false );

	if ( ! empty( $state['errors'] ) ) {
		return new WP_Error( 'sync_failed', $state['errors'][0] );
	}

	return $state;
}

function vch_motors_sync_fetch_export_page( $settings, $page, $updated_since ) {
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
		$query['updated_since'] = $updated_since;
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
	if ( $code < 200 || $code >= 300 ) {
		return new WP_Error( 'http_error', 'Inventory export request failed with status ' . $code );
	}

	$decoded = json_decode( $body, true );
	if ( ! is_array( $decoded ) || ( $decoded['status'] ?? '' ) !== 'ok' ) {
		return new WP_Error( 'invalid_payload', 'Inventory export payload was not in expected format.' );
	}

	$payload    = is_array( $decoded['data'] ?? null ) ? $decoded['data'] : array();
	$items      = is_array( $payload['items'] ?? null ) ? $payload['items'] : array();
	$pagination = is_array( $payload['pagination'] ?? null ) ? $payload['pagination'] : array();

	return array(
		'items'      => $items,
		'pagination' => $pagination,
	);
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

	$post_data = array(
		'post_type'    => $post_type,
		'post_status'  => 'publish',
		'post_title'   => $title,
		'post_content' => (string) ( $item['description'] ?? '' ),
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

	if ( empty( $item['available'] ) ) {
		update_post_meta( $post_id, 'car_mark_as_sold', 'on' );
	} else {
		delete_post_meta( $post_id, 'car_mark_as_sold' );
	}

	vch_motors_sync_apply_listing_attributes( $post_id, $post_type, $item );

	if ( ! empty( $settings['download_images'] ) ) {
		vch_motors_sync_attach_images( $post_id, $item );
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

function vch_motors_sync_value_for_attribute_slug( $slug, $item, $is_numeric ) {
	$slug = strtolower( (string) $slug );

	$boolean_map = array(
		'certified'    => ! empty( $item['certified'] ) ? 'Yes' : 'No',
		'single_owner' => ! empty( $item['single_owner'] ) ? 'Yes' : 'No',
		'clean_title'  => ! empty( $item['clean_title'] ) ? 'Yes' : 'No',
	);

	$value_map = array(
		'make'            => $item['make'] ?? null,
		'model'           => $item['model'] ?? null,
		'serie'           => $item['model'] ?? null,
		'trim'            => $item['trim'] ?? null,
		'year'            => $item['year'] ?? null,
		'body'            => $item['body_type'] ?? null,
		'body_type'       => $item['body_type'] ?? null,
		'drivetrain'      => $item['drivetrain'] ?? null,
		'drive'           => $item['drivetrain'] ?? null,
		'fuel_type'       => $item['fuel_type'] ?? null,
		'fuel'            => $item['fuel_type'] ?? null,
		'transmission'    => $item['transmission'] ?? null,
		'inventory_type'  => $item['inventory_type'] ?? null,
		'condition'       => $item['inventory_type'] ?? null,
		'mileage'         => $item['mileage'] ?? null,
		'odometer'        => $item['mileage'] ?? null,
		'city'            => $item['city'] ?? null,
		'state'           => $item['state'] ?? null,
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
		return $item['inventory_type'] ?? null;
	}
	if ( false !== strpos( $slug, 'dom' ) || false !== strpos( $slug, 'days' ) ) {
		return $item['days_on_market'] ?? null;
	}

	if ( $is_numeric ) {
		return null;
	}

	return null;
}

function vch_motors_sync_attach_images( $post_id, $item ) {
	$image_urls = vch_motors_sync_image_urls_from_item( $item );
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
			$attachment_id = vch_motors_sync_sideload_image( $url, $post_id );
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

function vch_motors_sync_image_urls_from_item( $item ) {
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

	return array_values( array_unique( array_filter( $normalized ) ) );
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

function vch_motors_sync_sideload_image( $url, $post_id ) {
	$temporary_file = download_url( $url, 45 );
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

function vch_motors_sync_to_float( $value ) {
	if ( null === $value || '' === $value ) {
		return null;
	}
	if ( ! is_numeric( $value ) ) {
		return null;
	}
	return round( (float) $value, 2 );
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
