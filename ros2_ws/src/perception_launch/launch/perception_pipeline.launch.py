# =============================================================================
# Launch file — starts the full perception pipeline:
#
#   test.mp4 → video_camera_node → segmentation_node → drivable_area_node
#
# Usage:
#   ros2 launch perception_launch perception_pipeline.launch.py \
#       video_path:=/absolute/path/to/test.mp4 \
#       model_path:=/absolute/path/to/segmentation_model_camvid.pt \
#       class_dict_path:=/absolute/path/to/label_colors.csv
# =============================================================================

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler, Shutdown
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():

    # ── Declare arguments so users can override paths from the CLI ──────
    video_path_arg = DeclareLaunchArgument(
        'video_path',
        default_value='test.mp4',
        description='Path to the input video file'
    )

    frames_dir_arg = DeclareLaunchArgument(
        'frames_dir',
        default_value='',
        description='Optional path to a directory of frames (overrides video_path)'
    )

    label_dir_arg = DeclareLaunchArgument(
        'label_dir',
        default_value='',
        description='Optional path to a directory of ground-truth label images'
    )

    model_path_arg = DeclareLaunchArgument(
        'model_path',
        default_value='segmentation_model_camvid.pt',
        description='Path to the TorchScript .pt model file'
    )

    class_dict_arg = DeclareLaunchArgument(
        'class_dict_path',
        default_value='label_colors.csv',
        description='Path to the label_colors.csv color mapping file'
    )

    # ── Node 1: Video Camera (C++) ──────────────────────────────────────
    video_camera_node = Node(
        package='video_camera_node_cpp',
        executable='video_camera_node',
        name='video_camera_node',
        output='screen',
        parameters=[{
            'video_path': LaunchConfiguration('video_path'),
            'frames_dir': LaunchConfiguration('frames_dir'),
            'label_dir': LaunchConfiguration('label_dir'),
        }]
    )

    # ── Node 2: Segmentation (Python) ──────────────────────────────────
    segmentation_node = Node(
        package='segmentation_node_py',
        executable='segmentation_node',
        name='segmentation_node',
        output='screen',
        parameters=[{
            'model_path': LaunchConfiguration('model_path'),
            'class_dict_path': LaunchConfiguration('class_dict_path'),
        }]
    )

    # ── Node 3: Drivable Area (C++) ────────────────────────────────────
    drivable_area_node = Node(
        package='drivable_area_node_cpp',
        executable='drivable_area_node',
        name='drivable_area_node',
        output='screen',
        parameters=[{
            'class_dict_path': LaunchConfiguration('class_dict_path'),
        }],
    )

    # ── When the video node exits, shut down the entire pipeline ────
    shutdown_on_video_end = RegisterEventHandler(
        OnProcessExit(
            target_action=video_camera_node,
            on_exit=[Shutdown(reason='Video playback completed.')]
        )
    )

    return LaunchDescription([
        video_path_arg,
        model_path_arg,
        class_dict_arg,
        video_camera_node,
        segmentation_node,
        drivable_area_node,
        shutdown_on_video_end,
    ])
