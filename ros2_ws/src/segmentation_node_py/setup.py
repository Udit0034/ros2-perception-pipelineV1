from setuptools import setup

package_name = 'segmentation_node_py'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@university.edu',
    description='TorchScript DeepLabV3 segmentation ROS2 node',
    license='MIT',
    entry_points={
        'console_scripts': [
            'segmentation_node = segmentation_node_py.segmentation_node:main',
        ],
    },
)
